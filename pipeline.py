"""Video processing pipeline: download -> find person -> cut -> stitch."""

import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass

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
# --- clip-start defaults ----------------------------------------------
# All three default to 0: nothing unverified is allowed near a clip's head.
# They are per-job sliders (see Tuning), so these are only the starting point.
# Historical values and what each one traded away are in HANDOFF.md 5a/5c.
#
# Matched samples this far apart still belong to the same clip. At 0 every
# sample is its own cluster, so each must clear ANCHOR_THRESHOLD on its own
# rather than inheriting an anchor from a neighbour -- borderline edge
# detections are dropped instead of extending a clip. Runs of consecutive
# samples are still rejoined by the re-merge in refine_intervals().
GROUP_GAP_SECONDS = 0.0
# Step used when walking clip boundaries outward to find the person's
# true entry/exit frame
REFINE_STEP = 0.12
# How far past a clip's first/last detection the boundary walk may extend.
# At 0 the walk is off and a clip begins exactly on a verified sample, which
# can be up to SAMPLE_INTERVAL late.
MAX_REFINE_EXTEND = 0.0
# Padding applied after refinement. START_PAD 0 means no footage precedes the
# first verified frame; negative values cut into it.
START_PAD = 0.0
END_PAD = 0.35
# Refined clips shorter than this are treated as false positives
MIN_CLIP_SECONDS = 0.5
# Frames are downscaled to this width for detection (speed)
DETECT_WIDTH = 960
# The final reel is cut from the best rendition up to this height; raise to
# 2160 for 4K output at the cost of much slower stitching
MAX_OUTPUT_HEIGHT = 1080
# Scanning/refinement run on a proxy no taller than this
PROXY_HEIGHT = 720

# --- auto-zoom ---------------------------------------------------------
# With zoom on, the source is pulled at up to 4K and the reel is written at
# 1080p, so a 2x crop is 1:1 pixels instead of an upscale. yt-dlp takes the
# best rendition at or below this, so 1080p-only videos simply stay 1080p.
ZOOM_SOURCE_HEIGHT = 2160
ZOOM_OUTPUT_HEIGHT = 1080
# Clips whose median face is at least this tall (fraction of frame height)
# are already close enough and are left alone. Measured over 1334 real
# detections: median 0.141, p10 0.090, p90 0.271.
ZOOM_TRIGGER_FACE_HEIGHT = 0.15
# Zoom aims to make the face this fraction of the *output* height
ZOOM_TARGET_FACE_HEIGHT = 0.30
# Never crop tighter than this; 2.0 is the point where a 4K source stops
# being able to fill 1080p without upscaling
MAX_ZOOM = 2.0
# Face centre sits this far down the crop, leaving headroom above and
# shoulders below rather than centring the face
ZOOM_FACE_TOP_BIAS = 0.38
# Spacing of the tracking pass; only runs over clips that survived refinement
ZOOM_SAMPLE_INTERVAL = 0.3


class PipelineError(Exception):
    """User-facing pipeline failure."""


def _clamp(value, low, high):
    return max(low, min(high, value))


@dataclass(frozen=True)
class Tuning:
    """Per-job options. Defaults reproduce the constants above, so an unset
    job behaves exactly as before.

    lead_in           padding before the first verified match; negative trims
                      *into* verified footage for a hard cut on entry
    boundary_reach    cap on how far the boundary walk may run outward; 0
                      disables refinement and pins clips to the coarse scan
    clip_gap          how far apart two matched samples can be and still be
                      one clip -- also the longest unverified stretch that can
                      sit inside one
    zoom              reframe wide clips around the subject; forces the reel to
                      a single height because concat needs matching dimensions
    hi_res            pull the source at up to 4K instead of 1080p. Independent
                      of zoom -- see _source_cap/_output_height for the four
                      combinations
    """

    lead_in: float = START_PAD
    boundary_reach: float = MAX_REFINE_EXTEND
    clip_gap: float = GROUP_GAP_SECONDS
    zoom: bool = False
    hi_res: bool = False

    @classmethod
    def clamped(cls, lead_in=None, boundary_reach=None, clip_gap=None,
                zoom=False, hi_res=False):
        """Build from untrusted (form) input, holding each value in range."""
        d = cls()
        return cls(
            lead_in=_clamp(d.lead_in if lead_in is None else lead_in, -0.5, 1.0),
            boundary_reach=_clamp(
                d.boundary_reach if boundary_reach is None else boundary_reach, 0.0, 3.0),
            clip_gap=_clamp(d.clip_gap if clip_gap is None else clip_gap, 0.0, 3.0),
            zoom=bool(zoom),
            hi_res=bool(hi_res),
        )


def _source_cap(tuning):
    """Tallest rendition to download. yt-dlp takes the best at or below this."""
    return ZOOM_SOURCE_HEIGHT if tuning.hi_res else MAX_OUTPUT_HEIGHT


def _output_height(tuning, source_height):
    """Height every segment is normalised to, or None to keep the source size.

    Only zoom forces a common height: cropped and uncropped segments have to
    agree on dimensions or the concat demuxer rejects the reel. Without zoom
    the segments already match, so nothing is rescaled.

        zoom + hi_res   4K source -> 1080p reel; a 2x crop is native pixels
        zoom only       1080p source -> 1080p reel; zoom is a real upscale
        hi_res only     4K source -> 4K reel; sharpest, slowest, largest
        neither         unchanged from the original pipeline
    """
    if not tuning.zoom:
        return None
    return min(ZOOM_OUTPUT_HEIGHT, source_height)


def _run(cmd, **kwargs):
    result = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip().splitlines()[-8:]
        raise PipelineError(f"Command failed ({cmd[0]}):\n" + "\n".join(tail))
    return result


def _ydl(format_spec, out_path, url):
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--no-playlist",
        # YouTube signs media URLs behind a JS player challenge. Solving it
        # needs both a JS runtime on PATH (deno) and yt-dlp's EJS solver
        # scripts, which are not bundled and are fetched once into the yt-dlp
        # cache. Without this flag the challenge fails and every download ends
        # in a hard 403 -- not the transient kind the retry below covers.
        "--remote-components", "ejs:github",
        "-f", format_spec,
        "--merge-output-format", "mp4",
        "-o", out_path,
        url,
    ]
    # YouTube intermittently 403s; one retry clears most transient failures
    try:
        _run(cmd)
    except PipelineError:
        time.sleep(3)
        _run(cmd)


def _video_title(url):
    """Best-effort title, for naming the download. Metadata only, no video
    bytes. Returns '' on any failure -- a missing title must not fail a job."""
    try:
        result = _run([sys.executable, "-m", "yt_dlp", "--no-playlist",
                       "--skip-download", "--quiet", "--no-warnings",
                       "--print", "%(title)s", url])
        return result.stdout.strip().splitlines()[0]
    except (PipelineError, IndexError):
        return ""


def _output_filename(title):
    """First 5 alphanumerics of the title plus a timestamp, so downloads from
    separate jobs don't overwrite each other in the browser's download folder."""
    slug = re.sub(r"[^A-Za-z0-9]", "", title or "")[:5].lower() or "reel"
    return f"{slug}-{time.strftime('%Y%m%d-%H%M%S')}.mp4"


def _video_height(path):
    result = _run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                   "-show_entries", "stream=height", "-of", "csv=p=0", path])
    try:
        return int(result.stdout.strip().splitlines()[0])
    except (ValueError, IndexError):
        return 0


def _decodable(path):
    """True when OpenCV can actually pull a frame out of the file.

    OpenCV bundles its own FFmpeg, and in the Linux wheels its AV1 decoder is
    hardware-only -- on a machine without AV1 hardware the file opens and then
    every read fails ("Failed to get pixel format"). yt-dlp now serves AV1 by
    default, so this has to be probed rather than assumed. The macOS wheel
    decodes AV1 in software, which is why this only ever bites in the
    container."""
    cap = cv2.VideoCapture(path)
    try:
        return bool(cap.isOpened() and cap.read()[0])
    finally:
        cap.release()


def _transcode_for_analysis(path, job_dir, progress):
    """Re-encode to H.264 so the scan can read it, using the system ffmpeg --
    it carries the software AV1/VP9 decoders that OpenCV's build lacks. Only
    reached when no H.264 rendition was available at all."""
    out = os.path.join(job_dir, "analysis.mp4")
    progress("download", 22, "Converting video to a readable format...")
    _run(["ffmpeg", "-y", "-i", path, "-an",
          # never upscale; the scan gains nothing from more pixels
          "-vf", f"scale=-2:'min({PROXY_HEIGHT},ih)'",
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", out])
    return out


def download_video(url, job_dir, progress, max_height=MAX_OUTPUT_HEIGHT):
    """Download the video at output quality plus, when the source is too large
    or cannot be decoded for analysis, a low-res H.264 proxy.
    Returns (source_path, proxy_path); they are the same file for small videos."""
    source = os.path.join(job_dir, "source.mp4")
    progress("download", 2, "Downloading video from YouTube...")
    # Codec deliberately unconstrained here: YouTube only publishes H.264 up to
    # 1080p, so demanding it would silently cap the 4K toggle at 1080p. Only
    # the system ffmpeg ever decodes this file, and it handles AV1 and VP9.
    _ydl(f"bv*[height<={max_height}]+ba/b[height<={max_height}]/b", source, url)
    if not os.path.exists(source):
        raise PipelineError("Download finished but no video file was produced.")

    if _video_height(source) <= PROXY_HEIGHT and _decodable(source):
        progress("download", 25, "Video downloaded.")
        return source, source

    # Scanning decodes every frame, so a video-only low-res proxy keeps it
    # fast. Unlike the source this asks for avc1 explicitly -- OpenCV reads
    # this one, and it cannot handle the AV1 yt-dlp would otherwise pick.
    proxy = os.path.join(job_dir, "proxy.mp4")
    progress("download", 18, "Downloading low-res proxy for analysis...")
    try:
        _ydl(f"bv*[height<={PROXY_HEIGHT}][vcodec^=avc1]"
             f"/b[height<={PROXY_HEIGHT}][vcodec^=avc1]"
             f"/bv*[height<={PROXY_HEIGHT}][ext=mp4]"
             f"/bv*[height<={PROXY_HEIGHT}]/b[height<={PROXY_HEIGHT}]",
             proxy, url)
    except PipelineError:
        proxy = source  # analysis falls back to the full-res file
    if not os.path.exists(proxy):
        proxy = source

    if not _decodable(proxy):
        converted = _transcode_for_analysis(proxy, job_dir, progress)
        if proxy != source:
            os.remove(proxy)  # the unreadable download is now dead weight
        proxy = converted

    progress("download", 25, "Video downloaded.")
    return source, proxy


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


def _best_match(matcher, ref_feat, frame):
    """(similarity, box) for the frame's best-matching face; box is None when
    no face was found. The box is normalised to the frame, so it carries from
    the proxy to the full-res source unchanged -- the same property that lets
    timestamps transfer between renditions."""
    scale = DETECT_WIDTH / frame.shape[1]
    if scale < 1:
        frame = cv2.resize(frame, None, fx=scale, fy=scale)
    h, w = frame.shape[:2]
    best, best_box = 0.0, None
    for face in matcher.detect(frame):
        score = matcher.similarity(ref_feat, matcher.embed(frame, face))
        if best_box is None or score > best:
            x, y, fw, fh = face[:4]
            best = score
            best_box = ((x + fw / 2) / w, (y + fh / 2) / h, fw / w, fh / h)
    return best, best_box


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
                score, _ = _best_match(matcher, ref_feat, frame)
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


def group_samples(samples, tuning=Tuning()):
    """Group matched (timestamp, score) samples into (first, last) clusters,
    keeping only clusters anchored by at least one high-confidence match."""
    groups = []
    for t, score in sorted(samples):
        if groups and t - groups[-1][1] <= tuning.clip_gap:
            groups[-1][1] = t
            groups[-1][2] = max(groups[-1][2], score)
        else:
            groups.append([t, t, score])
    return [(first, last) for first, last, best in groups if best >= ANCHOR_THRESHOLD]


def _match_at(cap, matcher, ref_feat, t):
    cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, t) * 1000)
    ok, frame = cap.read()
    return ok and _best_match(matcher, ref_feat, frame)[0] >= MATCH_THRESHOLD


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


def refine_intervals(matcher, video_path, ref_feat, groups, duration, progress,
                     tuning=Tuning()):
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
                                 max(0.0, first_t - tuning.boundary_reach))
        end = _extend_boundary(cap, matcher, ref_feat, last_t, +1,
                               min(duration, last_t + tuning.boundary_reach))
        # a negative lead_in cuts inside the verified match instead of ahead of it
        refined.append([max(0.0, start - tuning.lead_in), min(duration, end + END_PAD)])
    cap.release()

    merged = []
    for start, end in refined:
        # clips whose refined+padded edges (nearly) touch are one clip
        if merged and start <= merged[-1][1] + 0.25:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(s, e) for s, e in merged if e - s >= MIN_CLIP_SECONDS]


def track_subject(matcher, video_path, ref_feat, intervals, progress):
    """Median normalised face box per interval, or None where the subject was
    never located. Runs on the proxy -- normalised boxes carry to the source."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise PipelineError("Could not reopen the video to measure framing.")
    stats = []
    for i, (start, end) in enumerate(intervals):
        progress("track", 80 + 4 * i / len(intervals),
                 f"Measuring framing for clip {i + 1} of {len(intervals)}...")
        boxes = []
        t = start
        while t < end:
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, frame = cap.read()
            if ok:
                score, box = _best_match(matcher, ref_feat, frame)
                if box is not None and score >= MATCH_THRESHOLD:
                    boxes.append(box)
            t += ZOOM_SAMPLE_INTERVAL
        # median over the clip: robust to the odd frame where the detector
        # latches onto a bystander or the box wobbles
        stats.append(tuple(np.median(np.array(boxes), axis=0)) if boxes else None)
    cap.release()
    return stats


def plan_crops(stats):
    """Turn per-clip face measurements into normalised (x, y, size) crops.
    None means 'leave this clip alone' -- already tight enough, or unmeasured."""
    crops = []
    for box in stats:
        if box is None:
            crops.append(None)
            continue
        cx, cy, _, face_h = box
        if face_h >= ZOOM_TRIGGER_FACE_HEIGHT:
            crops.append(None)  # already a close enough shot
            continue
        # crop this fraction of the frame so the face lands at the target size,
        # never tighter than MAX_ZOOM allows
        size = _clamp(face_h / ZOOM_TARGET_FACE_HEIGHT, 1.0 / MAX_ZOOM, 1.0)
        if size > 0.98:
            crops.append(None)  # not enough zoom to be worth the re-encode
            continue
        # equal fractions of width and height preserve the source aspect ratio
        crops.append((_clamp(cx - size / 2, 0.0, 1.0 - size),
                      _clamp(cy - ZOOM_FACE_TOP_BIAS * size, 0.0, 1.0 - size),
                      size))
    return crops


def _video_size(path):
    result = _run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                   "-show_entries", "stream=width,height", "-of", "csv=p=0", path])
    w, h = result.stdout.strip().splitlines()[0].split(",")[:2]
    return int(w), int(h)


def _segment_filter(crop, source_size, out_height):
    """ffmpeg -vf for one segment, or None when the frame passes through."""
    parts = []
    if crop is not None:
        src_w, src_h = source_size
        x, y, size = crop
        # even dimensions keep libx264 happy
        cw = max(2, int(src_w * size) // 2 * 2)
        ch = max(2, int(src_h * size) // 2 * 2)
        cx = _clamp(int(src_w * x), 0, src_w - cw)
        cy = _clamp(int(src_h * y), 0, src_h - ch)
        parts.append(f"crop={cw}:{ch}:{cx}:{cy}")
    if out_height:
        # -2 keeps the aspect ratio and forces an even width, so cropped and
        # uncropped segments land on identical dimensions and concat accepts them
        parts.append(f"scale=-2:{out_height}:flags=lanczos")
        parts.append("setsar=1")
    return ",".join(parts) if parts else None


def cut_and_stitch(video_path, intervals, job_dir, progress, crops=None, out_height=None):
    """Cut each interval, concat into output.mp4. Returns the output path."""
    source_size = _video_size(video_path) if crops or out_height else None
    seg_paths = []
    for i, (start, end) in enumerate(intervals):
        seg = os.path.join(job_dir, f"seg_{i:04d}.mp4")
        crop = crops[i] if crops else None
        progress("stitch", 84 + 14 * i / len(intervals),
                 f"Cutting clip {i + 1} of {len(intervals)}"
                 + (" (zoomed)..." if crop else "..."))
        cmd = [
            "ffmpeg", "-y",
            "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}",
            "-i", video_path,
        ]
        vf = _segment_filter(crop, source_size, out_height)
        if vf:
            cmd += ["-vf", vf]
        cmd += [
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-c:a", "aac", "-ac", "2", "-ar", "44100",
            "-video_track_timescale", "90000",
            seg,
        ]
        _run(cmd)
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


def process_job(url, screenshot_path, job_dir, progress, tuning=None):
    """Full pipeline. Returns dict with output path and stats."""
    tuning = tuning or Tuning()
    matcher = FaceMatcher()

    progress("reference", 1, "Reading the face from your screenshot...")
    ref_feat = reference_embedding(matcher, screenshot_path)

    title = _video_title(url)
    video_path, proxy_path = download_video(url, job_dir, progress,
                                            _source_cap(tuning))

    progress("scan", 30, "Scanning video for the person...")
    samples, duration = scan_video(matcher, proxy_path, ref_feat, progress)
    if not samples:
        raise PipelineError(
            "The person was not found anywhere in the video. "
            "Try a clearer screenshot of their face."
        )

    groups = group_samples(samples, tuning)
    if not groups:
        raise PipelineError(
            "Some faces loosely resembled the screenshot, but none matched with "
            "high confidence — likely lookalikes, not the person. Try a sharper, "
            "more frontal screenshot of their face."
        )
    progress("refine", 70, "Refining clip boundaries...")
    intervals = refine_intervals(matcher, proxy_path, ref_feat, groups, duration,
                                 progress, tuning)
    if not intervals:
        raise PipelineError(
            "Only fleeting, sub-second matches were found — not enough for a clip. "
            "Try a clearer screenshot of the person's face."
        )
    crops = None
    out_height = _output_height(tuning, _video_size(video_path)[1])
    if tuning.zoom:
        progress("track", 80, "Measuring how much of the frame the subject fills...")
        crops = plan_crops(track_subject(matcher, proxy_path, ref_feat,
                                         intervals, progress))

    progress("stitch", 84, f"Found {len(intervals)} clip(s). Cutting and stitching...")
    output = cut_and_stitch(video_path, intervals, job_dir, progress, crops, out_height)

    if proxy_path != video_path:
        os.remove(proxy_path)
    os.remove(video_path)
    return {
        "output": output,
        "filename": _output_filename(title),
        "title": title,
        "clip_count": len(intervals),
        "source_duration": round(duration, 1),
        "output_duration": round(sum(e - s for s, e in intervals), 1),
        "zoomed_clips": sum(1 for c in crops if c) if crops else 0,
        "resolution": "x".join(str(v) for v in _video_size(output)),
    }
