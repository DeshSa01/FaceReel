# FaceReel

Web app that takes a YouTube URL plus a screenshot of a person from that video,
finds every moment the person appears, and stitches those clips into one
continuous playable video.

## Run locally

```bash
.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8765
```

Then open http://127.0.0.1:8765, paste a YouTube link, upload a clear
screenshot of the person's face, and wait for the stitched video to appear
in the player. One video is processed at a time.

## Run with Docker

Every push to `main` builds a `linux/amd64` image and pushes it to
`ghcr.io/deshsa01/facereel:latest` (`.github/workflows/docker.yml`). On the
host, one-time setup:

```bash
mkdir -p ~/facereel/storage
sudo chown -R 1000:1000 ~/facereel/storage   # the container runs as uid 1000
cp docker-compose.yml ~/facereel/
cd ~/facereel && docker compose up -d
```

Then open `http://<host>:8765`. To take a new build:

```bash
docker compose pull && docker compose up -d
```

Notes:

- **Run exactly one instance, one worker.** Job state lives in a module-level
  dict in `app.py` and the one-at-a-time rule is enforced in-process, so
  scaling out or adding `--workers` would break both.
- `./storage` is bind-mounted, so job scratch is visible on the host — but it
  is still wiped on every startup, same as a local run.
- Set `TZ` in the compose environment if you want reel filenames stamped in
  local time; the container defaults to UTC.
- Encoding is software libx264 (crf 18 / preset medium), unchanged from local.
  On a low-power host this is the slow part of a job.
- Pin `image:` to a `sha-<short>` tag instead of `latest` to roll back.

The first workflow run creates the GHCR package as **private** even though the
repo is public — flip it to public in the package settings, or `docker login
ghcr.io` on the host with a PAT that has `read:packages`.

### Bumping yt-dlp

YouTube changes break yt-dlp periodically. It is pinned in its own file,
`requirements-ytdlp.txt`, installed as the last layer of the image: edit the
version there, push, and the rebuild is seconds rather than a full reinstall.

## Requirements

Running locally:

- `ffmpeg` on PATH (installed via Homebrew)
- Python venv in `.venv` with the packages in `requirements.txt` (plus
  `requirements-ytdlp.txt`). The venv uses `opencv-python`; the image uses
  `opencv-python-headless`, which is the same `cv2` API without the GUI stack.
- Face models in `models/` (YuNet detector + SFace recognizer, from the
  [OpenCV model zoo](https://github.com/opencv/opencv_zoo))

Running under Docker, only Docker itself — `ffmpeg`, the Python deps, and the
models are all baked into the image.

## How it works

1. `yt-dlp` downloads the best rendition up to 1080p for the final cut (up to
   2160p with the 4K toggle), plus a 720p proxy used for analysis when the
   source is larger — so output quality doesn't slow down scanning.
2. YuNet detects the largest face in the screenshot; SFace turns it into a
   128-d reference embedding.
3. Frames are sampled every 0.5 s; every detected face is embedded and
   compared to the reference. Matching uses two thresholds (hysteresis):
   0.363 (OpenCV's published SFace same-person value) counts as a match, but
   a clip is only kept if it contains at least one high-confidence anchor
   match >= 0.45 — clusters of borderline-only matches are discarded as
   lookalike false positives.
4. Matched samples within **clip gap** seconds of each other are grouped into
   one clip, then each clip's boundaries are refined: the pipeline walks
   outward from the first/last detection in 0.12 s steps for as long as frames
   keep matching (tolerating one flickered miss, up to **boundary reach**), so
   clips start where the person actually enters instead of on blind padding.
   **Lead-in** / 0.35 s of padding is added around the verified boundaries;
   adjacent refined clips are re-merged if they touch, and clips shorter than
   0.5 s are dropped. The three bold values are the sliders below, all
   defaulting to 0.
5. With zoom on, each surviving clip is measured on the proxy and given a crop
   rectangle if the subject's face is under 15% of frame height.
6. `ffmpeg` re-encodes each interval from the full-quality file
   (frame-accurate cuts, near-transparent x264 crf 18 / preset medium),
   applying the crop where there is one, and concatenates them into
   `output.mp4`, served back to the page with range support.

Two independent toggles, both off by default:

- **Zoom in on the subject** reframes clips where the person fills little of the
  frame — a per-clip crop centred on them, triggered when their face is under
  15% of frame height. Forces the reel to a single height, since the concat
  demuxer needs every segment to match.
- **Download the source in 4K** raises the download cap from 1080p to 2160p.

Together they're the sharp combination: a 2× crop out of 4K is exactly
1920×1080, native pixels with no upscaling. Zoom alone still works but the crop
is a real upscale, so reframed clips look soft. 4K alone gives a 4K reel and no
reframing. The page shows which combination you've picked and what it produces.

The three knobs governing how much footage precedes a clip — **lead-in**,
**boundary reach**, and **clip gap** — are exposed per job under "Clip start
fine-tuning" on the form, so they can be dialled in without editing code. The
values used are shown alongside the result stats. All three default to **0**:
no unverified footage at a clip head, at the cost of clips starting up to 0.5s
late and borderline edge detections being dropped. **Use recommended** sets
0.15 / 0.6 / 0.6, measured to capture 100% of the genuine footage against 79.8%
at 0 / 0 / 0 — recall flattens at 0.6, so higher values add excess without
adding footage. Everything else is a
constant at the top of `pipeline.py`: match threshold,
sample interval, refine step, end padding, and output resolution cap
(`MAX_OUTPUT_HEIGHT`, default 1080 — raise to 2160 for 4K at the cost of
much slower stitching). Job artifacts live under `storage/jobs/<id>/`; the
downloaded source and proxy videos are deleted after processing.

Reels download as `<first 5 letters of the video title>-<timestamp>.mp4`, e.g.
`ricka-20260727-151225.mp4`, so repeated downloads don't overwrite each other.

**`storage/jobs/` is wiped on every startup.** Job state is in-memory, so
anything left on disk is orphaned once the server restarts. Download any reel
you want to keep before restarting.
