# FaceReel

Web app that takes a YouTube URL plus a screenshot of a person from that video,
finds every moment the person appears, and stitches those clips into one
continuous playable video.

## Run

```bash
.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8765
```

Then open http://127.0.0.1:8765, paste a YouTube link, upload a clear
screenshot of the person's face, and wait for the stitched video to appear
in the player. One video is processed at a time.

## Requirements

- `ffmpeg` on PATH (installed via Homebrew)
- Python venv in `.venv` with: fastapi, uvicorn, opencv-python, numpy,
  yt-dlp, python-multipart
- Face models in `models/` (YuNet detector + SFace recognizer, from the
  [OpenCV model zoo](https://github.com/opencv/opencv_zoo))

## How it works

1. `yt-dlp` downloads the best rendition up to 1080p for the final cut,
   plus a 720p proxy used for analysis when the source is larger — so
   output quality doesn't slow down scanning.
2. YuNet detects the largest face in the screenshot; SFace turns it into a
   128-d reference embedding.
3. Frames are sampled every 0.5 s; every detected face is embedded and
   compared to the reference. Matching uses two thresholds (hysteresis):
   0.363 (OpenCV's published SFace same-person value) counts as a match, but
   a clip is only kept if it contains at least one high-confidence anchor
   match >= 0.45 — clusters of borderline-only matches are discarded as
   lookalike false positives.
4. Matched samples within 1.2 s of each other are grouped into one clip, then
   each clip's boundaries are refined: the pipeline walks outward from the
   first/last detection in 0.12 s steps for as long as frames keep matching
   (tolerating one flickered miss, up to 3 s), so clips start where the person
   actually enters instead of on blind padding. Only 0.15 s / 0.35 s of
   padding is added around the verified boundaries; adjacent refined clips
   are re-merged if they touch, and clips shorter than 0.5 s are dropped.
5. `ffmpeg` re-encodes each interval from the full-quality file
   (frame-accurate cuts, near-transparent x264 crf 18 / preset medium) and
   concatenates them into `output.mp4`, served back to the page with range
   support.

Tuning knobs are constants at the top of `pipeline.py`: match threshold,
sample interval, refine step, padding, group gap, and output resolution cap
(`MAX_OUTPUT_HEIGHT`, default 1080 — raise to 2160 for 4K at the cost of
much slower stitching). Job artifacts live under `storage/jobs/<id>/`; the
downloaded source and proxy videos are deleted after processing.
