"""Video processing pipeline: download -> find person -> cut -> stitch."""

import os
import subprocess
import sys
import time

import cv2
import numpy as np

MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")
YUNET_PATH = os.path.join(MODELS_DIR, "yunet.onnx")
SFACE_PATH = os.path.join(MODELS_DIR, "sface.onnx")

# Official OpenCV SFace cosine-similarity threshold for "same person"; used
# for grouping and boundary extension once a clip is anchored
MATCH_THRESHOLD = 0.363
# A clip must contain at least one match this strong; clusters with only
# borderline matches are discarded as lookalike false positives
ANCHOR_THRESHOLD = 0.45
# Seconds between sampled frames when scanning the video
SAMPLE_INTERVAL = 0.5
# Matched samples this far apart still belong to the same clip (kept small so
# no long unverified gap can hide inside a clip; refinement re-merges clips
# that are actually continuous)
GROUP_GAP_SECONDS = 1.2
# Step used when walking clip boundaries outward to find the person's
# true entry/exit frame
REFINE_STEP = 0.12
# How far past a clip's first/last detection the boundary walk may extend
MAX_REFINE_EXTEND = 3.0
# Small padding applied after refinement
START_PAD = 0.15
END_PAD = 0.35
# Refined clips shorter than this are treated as false positives
MIN_CLIP_SECONDS = 0.5
# Frames are downscaled to this width for detection (speed)
DETECT_WIDTH = 960


class PipelineError(Exception):
    """User-facing pipeline failure."""


def _run(cmd, **kwargs):
    result = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip().splitlines()[-8:]
        raise PipelineError(f"Command failed ({cmd[0]}):\n" + "\n".join(tail))
    return result


def download_video(url, job_dir, progress):
    """Download the YouTube video (<=720p mp4). Returns the file path."""
    out_path = os.path.join(job_dir, "source.mp4")
    progress("download", 2, "Downloading video from YouTube...")
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--no-playlist",
        "-f", "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720][ext=mp4]/b[height<=720]/b",
        "--merge-output-format", "mp4",
        "-o", out_path,
        url,
    ]
    # YouTube intermittently 403s; one retry clears most transient failures
    try:
        _run(cmd)
    except PipelineError:
        progress("download", 5, "Download failed, retrying once...")
        time.sleep(3)
        _run(cmd)
    if not os.path.exists(out_path):
        raise PipelineError("Download finished but no video file was produced.")
    progress("download", 25, "Video downloaded.")
    return out_path


class FaceMatcher:
    def __init__(self):
        self.detector = cv2.FaceDetectorYN.create(YUNET_PATH, "", (320, 320), 0.6, 0.3, 5000)
        self.recognizer = cv2.FaceRecognizerSF.create(SFACE_PATH, "")

    def detect(self, image):
        """Returns Nx15 face array (or empty list) for a BGR image."""
        h, w = image.shape[:2]
        self.detector.setInputSize((w, h))
        _, faces = self.detector.detect(image)
        return faces if faces is not None else []

    def embed(self, image, face):
        aligned = self.recognizer.alignCrop(image, face)
        return self.recognizer.feature(aligned)

    def similarity(self, feat_a, feat_b):
        a = feat_a.flatten().astype(np.float64)
        b = feat_b.flatten().astype(np.float64)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-10))


def reference_embedding(matcher, screenshot_path):
    """Embedding of the largest face in the screenshot."""
    image = cv2.imread(screenshot_path)
    if image is None:
        raise PipelineError("Could not read the screenshot image.")
    # YuNet degrades on very large inputs; cap the long side
    scale = 1280 / max(image.shape[:2])
    if scale < 1:
        image = cv2.resize(image, None, fx=scale, fy=scale)
    faces = matcher.detect(image)
    if len(faces) == 0:
        raise PipelineError(
            "No face found in the screenshot. Use a clear, front-facing crop of the person."
        )
    largest = max(faces, key=lambda f: f[2] * f[3])
    return matcher.embed(image, largest)


def _best_similarity(matcher, ref_feat, frame):
    """Highest similarity between the reference and any face in the frame."""
    scale = DETECT_WIDTH / frame.shape[1]
    if scale < 1:
        frame = cv2.resize(frame, None, fx=scale, fy=scale)
    best = 0.0
    for face in matcher.detect(frame):
        feat = matcher.embed(frame, face)
        best = max(best, matcher.similarity(ref_feat, feat))
    return best


def scan_video(matcher, video_path, ref_feat, progress):
    """Sample frames and return sorted timestamps (s) where the person appears."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise PipelineError("Could not open the downloaded video.")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps if fps else 0
    step = max(1, round(fps * SAMPLE_INTERVAL))

    matches = []
    frame_idx = 0
    while True:
        if not cap.grab():
            break
        if frame_idx % step == 0:
            ok, frame = cap.retrieve()
            if ok:
                score = _best_similarity(matcher, ref_feat, frame)
                if score >= MATCH_THRESHOLD:
                    matches.append((frame_idx / fps, score))
            if total_frames > 0 and frame_idx % (step * 20) == 0:
                pct = 30 + 40 * frame_idx / total_frames
                progress("scan", pct,
                         f"Scanning {frame_idx / fps:.0f}s / {duration:.0f}s "
                         f"({len(matches)} matched frames)")
        frame_idx += 1
    cap.release()
    return matches, duration


def group_samples(samples):
    """Group matched (timestamp, score) samples into (first, last) clusters,
    keeping only clusters anchored by at least one high-confidence match."""
    groups = []
    for t, score in sorted(samples):
        if groups and t - groups[-1][1] <= GROUP_GAP_SECONDS:
            groups[-1][1] = t
            groups[-1][2] = max(groups[-1][2], score)
        else:
            groups.append([t, t, score])
    return [(first, last) for first, last, best in groups if best >= ANCHOR_THRESHOLD]


def _match_at(cap, matcher, ref_feat, t):
    cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, t) * 1000)
    ok, frame = cap.read()
    return ok and _best_similarity(matcher, ref_feat, frame) >= MATCH_THRESHOLD


def _extend_boundary(cap, matcher, ref_feat, t0, direction, limit_t):
    """Walk from t0 (direction -1 = backward, +1 = forward) while frames keep
    matching, tolerating one isolated miss. Returns the furthest matching time."""
    edge = t0
    t = t0 + direction * REFINE_STEP
    misses = 0
    while (t - limit_t) * direction <= 0:
        if _match_at(cap, matcher, ref_feat, t):
            edge = t
            misses = 0
        else:
            misses += 1
            if misses > 1:
                break
        t += direction * REFINE_STEP
    return edge


def refine_intervals(matcher, video_path, ref_feat, groups, duration, progress):
    """Walk each clip's boundaries outward in fine steps to find the person's
    actual entry/exit, so clips don't start before the person appears."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise PipelineError("Could not reopen the video for boundary refinement.")
    refined = []
    for i, (first_t, last_t) in enumerate(groups):
        progress("refine", 70 + 10 * i / len(groups),
                 f"Refining clip {i + 1} of {len(groups)} boundaries...")
        start = _extend_boundary(cap, matcher, ref_feat, first_t, -1,
                                 max(0.0, first_t - MAX_REFINE_EXTEND))
        end = _extend_boundary(cap, matcher, ref_feat, last_t, +1,
                               min(duration, last_t + MAX_REFINE_EXTEND))
        refined.append([max(0.0, start - START_PAD), min(duration, end + END_PAD)])
    cap.release()

    merged = []
    for start, end in refined:
        # clips whose refined+padded edges (nearly) touch are one clip
        if merged and start <= merged[-1][1] + 0.25:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(s, e) for s, e in merged if e - s >= MIN_CLIP_SECONDS]


def cut_and_stitch(video_path, intervals, job_dir, progress):
    """Cut each interval, concat into output.mp4. Returns the output path."""
    seg_paths = []
    for i, (start, end) in enumerate(intervals):
        seg = os.path.join(job_dir, f"seg_{i:04d}.mp4")
        progress("stitch", 80 + 18 * i / len(intervals),
                 f"Cutting clip {i + 1} of {len(intervals)}...")
        _run([
            "ffmpeg", "-y",
            "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}",
            "-i", video_path,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-c:a", "aac", "-ac", "2", "-ar", "44100",
            "-video_track_timescale", "90000",
            seg,
        ])
        seg_paths.append(seg)

    list_path = os.path.join(job_dir, "segments.txt")
    with open(list_path, "w") as f:
        for p in seg_paths:
            # concat demuxer resolves relative paths against the list file, not cwd
            f.write(f"file '{os.path.abspath(p)}'\n")

    output = os.path.join(job_dir, "output.mp4")
    _run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path,
        "-c", "copy", "-movflags", "+faststart",
        output,
    ])
    for p in seg_paths:
        os.remove(p)
    os.remove(list_path)
    return output


def process_job(url, screenshot_path, job_dir, progress):
    """Full pipeline. Returns dict with output path and stats."""
    matcher = FaceMatcher()

    progress("reference", 1, "Reading the face from your screenshot...")
    ref_feat = reference_embedding(matcher, screenshot_path)

    video_path = download_video(url, job_dir, progress)

    progress("scan", 30, "Scanning video for the person...")
    timestamps, duration = scan_video(matcher, video_path, ref_feat, progress)
    if not timestamps:
        raise PipelineError(
            "The person was not found anywhere in the video. "
            "Try a clearer screenshot of their face."
        )

    groups = group_samples(timestamps)
    if not groups:
        raise PipelineError(
            "Some faces loosely resembled the screenshot, but none matched with "
            "high confidence — likely lookalikes, not the person. Try a sharper, "
            "more frontal screenshot of their face."
        )
    progress("refine", 70, "Refining clip boundaries...")
    intervals = refine_intervals(matcher, video_path, ref_feat, groups, duration, progress)
    if not intervals:
        raise PipelineError(
            "Only fleeting, sub-second matches were found — not enough for a clip. "
            "Try a clearer screenshot of the person's face."
        )
    progress("stitch", 80, f"Found {len(intervals)} clip(s). Cutting and stitching...")
    output = cut_and_stitch(video_path, intervals, job_dir, progress)

    os.remove(video_path)
    return {
        "output": output,
        "clip_count": len(intervals),
        "source_duration": round(duration, 1),
        "output_duration": round(sum(e - s for s, e in intervals), 1),
    }
