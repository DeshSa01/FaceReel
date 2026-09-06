# FaceReel — Handoff

Context document for resuming work in a fresh session. Covers what the app is,
how it works, why it works that way, and what's still open.

Repo: https://github.com/DeshSa01/FaceReel (branch `main`, all work pushed)
Local path: `/Users/sandesh/projects/video-stitcher` (directory name predates the rename)

> **Starting a new session? Read §15 first.** The next piece of work is the reel
> archive: fully specced, not yet built, with its tasks in
> `specs/001-reel-archive/tasks.md`. §14 covers how the app is deployed and the
> three environment gaps that bit during containerisation — worth reading before
> changing anything that touches downloads or video decoding.

---

## 1. What it does

Web app. User submits a **YouTube URL** + a **screenshot of a person's face**
from that video. The app finds every moment that person appears and stitches
those segments into one continuous video, played back in the browser.

One video is processed at a time (a second submission gets HTTP 409).

Form options: three clip-boundary sliders with a "Use recommended" preset
(§11), plus **Zoom in on the subject** and **Download the source in 4K** (§12).

## 2. Stack & environment

| Piece | Choice | Notes |
|---|---|---|
| Python | `/opt/homebrew/bin/python3.14`, venv at `.venv` | System python is 3.9 — do not use it |
| Web | FastAPI + uvicorn | `.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8765` |
| Face detect | OpenCV `FaceDetectorYN` (YuNet) | `models/yunet.onnx` |
| Face recognize | OpenCV `FaceRecognizerSF` (SFace) | `models/sface.onnx`, 128-d embeddings |
| Video | `ffmpeg` / `ffprobe` (Homebrew), `yt-dlp` | |
| JS runtime | `deno` (Homebrew locally, pinned 2.9.5 in the image) | **Required** — YouTube 403s without it (§14) |
| Frontend | Single static HTML file, vanilla JS | `static/index.html` |
| Container | `python:3.14-slim` + ffmpeg + deno | `Dockerfile`; deps pinned as a full closure |
| Registry | `ghcr.io/deshsa01/facereel` | Built by GitHub Actions on push to `main` |
| Deployment | Portainer stack on an ACEMAGIC N95 (Proxmox) | `docker-compose.yml`; storage bind-mounted |
| Planning | GitHub spec-kit | `.specify/`, `specs/`, constitution v1.0.0 |

**Why YuNet/SFace and not InsightFace/dlib/face_recognition:** they ship inside
OpenCV with no extra native deps, which avoids build pain on Python 3.14 / arm64.
Both ONNX files are committed to the repo so clone-and-run works.

Models came from the [OpenCV model zoo](https://github.com/opencv/opencv_zoo)
(`face_detection_yunet_2023mar.onnx`, `face_recognition_sface_2021dec.onnx`).

## 3. Files

- `pipeline.py` — all processing. Pure functions + `process_job()` orchestrator.
  Raises `PipelineError` for anything the user should see.
- `app.py` — FastAPI: `POST /api/jobs`, `GET /api/jobs/{id}`,
  `GET /api/jobs/{id}/output`, `GET /`. Jobs run on a background thread; state
  is an in-memory dict (lost on restart — deliberate, single-user local tool).
- `static/index.html` — form, live progress bar, `<video>` player, download link.
  Light/dark themed.
- `models/` — the two ONNX files.
- `Dockerfile`, `.dockerignore`, `docker-compose.yml`,
  `.github/workflows/docker.yml` — the container and its CI (§14).
- `requirements.txt` — **full pinned closure**, transitive packages included.
  `requirements-ytdlp.txt` is separate on purpose: it is the last image layer,
  so bumping yt-dlp rebuilds in seconds (§14).
- `.specify/` — spec-kit scripts, templates, and the project constitution.
  `specs/<NNN>-<name>/` — per-feature spec / plan / tasks (§15).
- `archive.py` — **does not exist yet**; the next feature creates it (§15).
- `storage/jobs/<job_id>/` — per-job scratch: screenshot, source video, proxy,
  segments, `output.mp4`. Source + proxy are deleted on success; `output.mp4`
  stays for the life of the process (it's what gets served) but is **wiped at
  the next startup** by `clean_jobs_dir()` (§13). Gitignored.

## 4. Pipeline stages

`process_job()` runs these in order, reporting progress via a callback whose
`stage` string drives the UI label:

1. **`reference`** — read screenshot, detect faces, take the **largest** face,
   embed it. Screenshot is downscaled so its long side is ≤1280 first (YuNet
   degrades on very large inputs). Errors if no face found.
2. **`download`** — see proxy workflow below.
3. **`scan`** — decode the proxy, sample a frame every `SAMPLE_INTERVAL` (0.5s),
   detect all faces, embed each, keep the **best** similarity per frame. Frames
   scoring ≥ `MATCH_THRESHOLD` are recorded as `(timestamp, score)`.
4. **`refine`** — group samples into clips, then walk each clip's boundaries
   frame-by-frame to find true entry/exit (below).
5. **`track`** — only when auto-zoom is on (§12): measures how much of the frame
   the subject fills in each surviving clip, on the proxy.
6. **`stitch`** — cut each interval from the **full-resolution** source with
   ffmpeg (re-encode for frame accuracy), optionally cropping to the zoom
   rectangle, then concat-copy into `output.mp4` with `+faststart`.

## 5. The three design decisions that matter

These were each driven by a specific observed defect. Don't undo them without
understanding what they fixed.

### 5a. Boundary refinement (fixes: clips starting before the person appears)

**Problem:** originally every matched timestamp got blind ±0.75s padding, and
0.5s sampling meant the first detection could already be late — so clips opened
with up to ~1.25s of footage without the person.

**Fix:** the coarse scan only locates *clusters*. For each cluster,
`_extend_boundary()` walks outward from the first/last detection in
`REFINE_STEP` (0.12s) increments, seeking with `CAP_PROP_POS_MSEC` and
re-checking the face each step. It keeps extending while frames match,
tolerating **one** isolated miss (flicker/blink/motion blur), up to
`MAX_REFINE_EXTEND` (3s). Only then is a small pad applied:
`START_PAD` 0.15s / `END_PAD` 0.35s.

Net effect: a clip starts at most 0.15s before a frame where the person is
*verifiably* on screen.

**Caveat found 2026-07-27:** `misses` resets to 0 on every match, so "one
isolated miss" only bounds a *run* of misses. Alternating match/miss flicker
never trips `misses > 1`, and the walk runs the full `MAX_REFINE_EXTEND` —
measured at **2.76s of flicker pulled into a clip head** with the default 3.0s
reach. The `boundary_reach` slider caps this; making `misses` cumulative per
walk would fix it properly, at some cost to genuine blink/blur tolerance.

### 5b. Two-threshold hysteresis (fixes: lookalike faces matching)

**Problem:** other faces (reported as female faces in the user's real video)
scored just above the standard threshold and produced junk clips.

**Fix:** two thresholds instead of raising the one.
- `MATCH_THRESHOLD` **0.363** — OpenCV's published SFace same-person value.
  Counts as a match for grouping and boundary extension.
- `ANCHOR_THRESHOLD` **0.45** — a cluster is **discarded entirely** unless it
  contains at least one match this strong.

Raising the single threshold instead would have cost recall at clip edges where
faces are small or angled. Hysteresis keeps edges accurate while killing
borderline-only clusters.

### 5c. Small group gap + re-merge (fixes: 2s of non-matching footage inside clips)

**Problem:** `GROUP_GAP_SECONDS` was 3.0, and the gap between two grouped
samples was **never verified** — one stray false positive 2–3s before the real
entry dragged the whole unverified stretch into the clip.

**Fix:** gap cut to **1.2s**. Boundary refinement then re-merges neighbouring
clips only when frame-by-frame checks prove the person is present in between
(clips whose refined+padded edges come within 0.25s are merged). Clips shorter
than `MIN_CLIP_SECONDS` (0.5s) are dropped as false positives.

**Still only a mitigation, not a cure.** The re-merge check applies *between*
clusters. A gap *inside* a cluster is never verified: `group_samples()` will
absorb any sample within `clip_gap` of the previous one, and `refine_intervals()`
only walks a cluster's outer edges. A single weak false positive 1.0s before
the real entry still becomes the clip start. Verified 2026-07-27 —
`group_samples([(10.0, 0.37), (11.0, 0.55), ...])` yields one cluster starting
at 10.0s. The proper fix is to verify interior gaps and split clusters that
fail; until then the `clip_gap` slider bounds the damage.

### 5d. Proxy workflow (quality without slowing analysis)

Output was capped at 720p because scanning cost scales with resolution.
Now `download_video()` returns `(source_path, proxy_path)`:

- **Source**: best rendition ≤ `MAX_OUTPUT_HEIGHT` (1080). Used only for the
  final cut.
- **Proxy**: video-only rendition ≤ `PROXY_HEIGHT` (720), downloaded **only if**
  the source is taller. Used for scan + refine. Timestamps are identical between
  renditions, so intervals transfer directly.
- If the proxy download fails, analysis falls back to the source file.
- Small videos (≤720p) skip the second download; both paths are the same file.

Detection also downscales frames to `DETECT_WIDTH` (960px) regardless — higher
resolution does not improve face matching.

Encode settings for segments: **crf 18, preset medium** (was crf 23/veryfast).

## 6. Tuning knobs (all at top of `pipeline.py`)

| Constant | Value | Effect if changed |
|---|---|---|
| `MATCH_THRESHOLD` | 0.363 | Lower = more recall, more false positives |
| `ANCHOR_THRESHOLD` | 0.45 | **Raise to 0.5 if lookalikes still slip through** |
| `SAMPLE_INTERVAL` | 0.5 | Lower = catch shorter appearances, slower scan |
| `GROUP_GAP_SECONDS` | **0.0** | Raise = fewer/longer clips, risks unverified gaps |
| `REFINE_STEP` | 0.12 | Lower = tighter boundaries, slower refine |
| `MAX_REFINE_EXTEND` | **0.0** | How far a boundary walk may run |
| `START_PAD` / `END_PAD` | **0.0** / 0.35 | Raise `START_PAD` for more lead-in context |

The three that decide how much footage precedes a clip are **also per-job
sliders** (see §11); the constants above are just their defaults.
| `MIN_CLIP_SECONDS` | 0.5 | Minimum surviving clip length |
| `DETECT_WIDTH` | 960 | Detection downscale width |
| `MAX_OUTPUT_HEIGHT` | 1080 | **2160 for 4K** — much slower stitching |
| `PROXY_HEIGHT` | 720 | Analysis rendition cap |
| crf/preset | 18 / medium | In `cut_and_stitch()`; crf 20–21 for smaller files |

## 7. Known behaviour & limitations

- **Face-only.** Moments where the person is on screen but turned away or too
  small to recognize are excluded — a clip starts at the first *recognizable*
  frame. This is correct per the requirement but does split clips (e.g. one test
  video splits into 2 clips, dropping a ~2s face-away stretch).
- **Largest face wins** if the screenshot contains several people.
- **Output files are large** — 1080p crf 18 is ~5× the old 720p crf 23 bitrate
  (a 134s reel came out ~103 MB, ~6 Mbps).
- **Above 720p YouTube serves VP9/AV1**, so the source download may be webm.
  Harmless — ffmpeg decodes it and segments are re-encoded to H.264.
- **Jobs are in-memory**: restarting uvicorn loses job history. Since anything
  left on disk is therefore orphaned, `clean_jobs_dir()` now **deletes every
  job folder at startup** (see §13) — `output.mp4` files no longer survive a
  restart. Since the persistent-job-progress feature, this has a user-visible
  side effect: a reel in flight during a restart is not silently lost from
  view — `facereel.watching` (client-side, `static/progress.js`) notices the
  reel is gone from `GET /api/jobs/active` and reports it as not finished,
  rather than leaving the bottom bar frozen at its last percentage or making
  it vanish as if the reel had completed.
- **yt-dlp 403s intermittently** on YouTube. `_ydl()` retries once after 3s,
  which clears essentially all of it. Must invoke the venv's yt-dlp via
  `sys.executable -m yt_dlp`, not the Homebrew binary.
- **ffmpeg concat demuxer** resolves relative paths in the list file against the
  *list file's* directory, not cwd — `segments.txt` therefore holds absolute
  paths. This caused a real bug; don't "simplify" it back.

## 8. Naming wart — fixed

`process_job()` now calls the `scan_video()` result `samples`, not `timestamps`.

## 9. How this has been verified

Each change was checked by driving the real pipeline, not just unit tests:

- **End-to-end through the HTTP API** — submit job, poll progress, download
  output, `ffprobe` the result for codec/resolution/duration. Also verified
  HTTP range requests (206) work, since the browser player needs them.
- **Synthetic lead-in video** — black video concatenated before real footage, to
  measure exactly where a clip starts vs. when the person truly enters.
  (Boundary refinement result: clip started at 4.71s for a 4.0s entry.)
- **Cross-person negative test** — scored a different person's video against the
  reference: max similarity 0.336, below even the weak threshold, zero clips.
- **Two-person composite** — other person for 30s then the target; output clips
  began at 29.89s, i.e. only the 0.15s pad before real entry.
- **Small-video regression** — a ≤720p video to exercise the no-proxy path.
- **1080p real job** — 3.5-min music video → 25 clips, 134s, verified 1920×1080.

Useful test assets can be rebuilt with `yt-dlp --download-sections` plus an
`ffmpeg` concat filter; nothing test-related is committed.

## 10. Open ideas (discussed, not built)

- Surface **per-clip confidence scores** in the UI to make threshold tuning
  easier for the user.
- Raise `ANCHOR_THRESHOLD` to 0.5 if lookalikes still appear in real videos.
- Multi-reference support (several screenshots of the same person, averaged or
  max-scored) would improve recall on profile/angled shots.
- ~~Persist job state so restarts don't orphan finished outputs.~~ Settled the
  other way: §13 deletes orphans at startup instead of persisting them.
- Expose `ANCHOR_THRESHOLD` and `SAMPLE_INTERVAL` as controls. The sliders only
  move clip *edges*; these two decide whether an appearance is found at all, so
  they are what you need when whole appearances go missing rather than seconds.
- Expose `END_PAD` (0.35, still hardcoded). Every slider addresses clip *heads*;
  nothing trims the non-matching tail.
- Dynamic zoom tracking — see §12 known limits.

---

## 11. Per-job tuning sliders (added 2026-07-27)

`pipeline.Tuning` is a frozen dataclass whose defaults *are* the module
constants, threaded through `process_job` → `group_samples` / `refine_intervals`.
Omitting it anywhere reproduces the old behaviour exactly, so every function
keeps a `tuning=Tuning()` default.

| Slider | Field | Range | Default | Bounds which defect |
|---|---|---|---|---|
| Lead-in | `lead_in` | −0.5 … 1.0 | **0.0** | the flat pad; **negative trims into** verified footage for a hard entry cut |
| Boundary reach | `boundary_reach` | 0 … 3.0 | **0.0** | the §5a flicker walk; at 0 refinement is off entirely |
| Clip gap | `clip_gap` | 0 … 3.0 | **0.0** | the §5c unverified interior gap |

### Defaults changed to 0/0/0 on 2026-07-27

Deliberate: nothing unverified may sit at a clip head. The original
0.15 / 3.0 / 1.2 remains the *documented* behaviour of §5a–5c, but is no longer
the default. What each zero does:

- **`clip_gap` 0 does not shatter clips.** Every sample becomes its own cluster,
  but the 0.25s re-merge in `refine_intervals()` rejoins consecutive ones —
  `END_PAD` (0.35) + 0.25 comfortably spans the 0.5s sample spacing. Measured: 7
  single-sample clusters → **1** clip. An earlier note in this file warned that
  gaps ≤0.5 shatter clips; that was wrong, it overlooked the re-merge.
- **What `clip_gap` 0 really changes is the anchor rule.** With no grouping, a
  sample can't inherit an anchor from a neighbour, so every retained detection
  must clear `ANCHOR_THRESHOLD` (0.45) alone. Borderline edge detections
  (0.363–0.45) are dropped rather than extending a clip. This is the main recall
  cost, not fragmentation.
- **`boundary_reach` 0 makes clips start up to `SAMPLE_INTERVAL` (0.5s) late**,
  since nothing walks back to the true entry.

Measured on a synthetic case (person on screen 9.6–13.2s, one weak false
positive at 8.0s, one borderline edge sample at 13.5s):

| | old 0.15/3.0/1.2 | new 0/0/0 |
|---|---|---|
| clips | 1 | 1 |
| interval | 9.49 – 13.85 | 10.00 – 13.35 |
| footage before true entry | 0.11s | **0.00s** |
| genuine footage lost at head | 0.00s | 0.40s |

To go back to catching those late starts without reintroducing the flicker walk,
raise `boundary_reach` to ~0.6 (just over `SAMPLE_INTERVAL`); raise `clip_gap` to
~0.6 to let borderline edge frames extend clips again.

### The "Use recommended" toggle: 0.15 / 0.6 / 0.6

Ticking it sets the sliders to the **recall-optimal** point. Measured against a
synthetic ground truth (person on screen 9.4–13.6s, one false positive at 8.0s,
borderline genuine detections at 9.5s and 13.5s):

| lead / reach / gap | genuine footage captured | excess |
|---|---|---|
| 0 / 0 / 0 (default) | 79.8% | 0.00s |
| 0 / 0.6 / 0.6 | 97.6% | 0.25s |
| **0.15 / 0.6 / 0.6** | **100%** | **0.30s** |
| 0.15 / 3.0 / 1.2 (original) | 100% | 0.30s |
| 0.3 / 3.0 / 2.0 | 100% | 1.95s |

**Recall flattens at 0.6.** Once the walk can bridge `SAMPLE_INTERVAL` and the
gap can group consecutive samples, everything the scan found is already
captured — 3.0/1.2 adds not one frame, and on real flickery footage 3.0 is what
dragged in 2.76s of junk. Of the 0.30s excess only 0.05s is at the head; the
other 0.25s is the `END_PAD` tail, which no slider touches.

The checkbox **reflects** the sliders rather than driving them: moving any
slider unticks it, and moving back onto the recommended values re-ticks it, so
it can never claim "recommended" while the values disagree. Purely client-side —
`recommended` in `static/index.html` alongside `knobs`; the API already accepts
arbitrary values, so no server change was needed.

`Tuning.clamped()` holds untrusted form values in range — `app.py` passes the
raw floats straight from the multipart form, so don't bypass it. The chosen
values are stored on the job dict and echoed by `GET /api/jobs/{id}`, which is
what lets the UI print them under the result stats; useful when comparing runs.

Front end is a `<details open>` panel above the submit button, plus a reset
button. The `knobs` object in `static/index.html` duplicates the three defaults
— keep it in sync with `Tuning` if you change them.

`GET /` now sends `Cache-Control: no-cache`. Without it `FileResponse` sets only
ETag/Last-Modified, browsers cache the page heuristically, and UI changes appear
not to deploy across restarts. `FileResponse` ignores `If-None-Match`, so this
re-sends the 10 KB page each load rather than 304ing; not worth fixing locally.

---

## 12. Auto-zoom (added 2026-07-27)

`Tuning.zoom` reframes clips where the subject is small. Off by default; the
entire feature is inert when off (`_segment_filter` returns `None`, so the
ffmpeg command is byte-identical to before).

### Why the threshold is on face *height*, not area

The original idea was "zoom if the subject covers <30% of the frame". Measured
over 1334 real detections across three finished reels:

| face **area** % of frame | median 0.85 · p90 3.08 · max ever 13.33 |
|---|---|
| frames reaching 30% area | **0 of 1334** |

30% area means a face ~63% of frame *height* — an extreme close-up. The rule
would have fired on every frame. Face **height** is well-behaved (median 0.141,
p10 0.090, p90 0.271), so `ZOOM_TRIGGER_FACE_HEIGHT` is 0.15 — just above the
median, so roughly the wider half of clips get zoomed.

If you ever want true *body* coverage, a body box can be estimated from the face
(~3× width, ~7× height) without new dependencies; 30% is a sensible threshold on
that measure. Not implemented.

### The two toggles are independent

`zoom` and `hi_res` are separate flags; `_source_cap()` and `_output_height()`
are the only places that read them, so the matrix lives in one spot:

| zoom | hi_res | download cap | reel | notes |
|---|---|---|---|---|
| ✓ | ✓ | 2160 | 1080p | 2× crop is **native pixels**, no upscale. Slowest. |
| ✓ | ✗ | 1080 | 1080p | zoom is a **real upscale** — reframed clips look soft |
| ✗ | ✓ | 2160 | source (4K) | sharpest, largest files, no reframing |
| ✗ | ✗ | 1080 | source | original pipeline, untouched |

**Only zoom forces a reel height.** The concat demuxer requires identical
dimensions on every segment, and zoom is what makes them differ. Without zoom,
`_output_height()` returns `None` and no `scale` filter is emitted at all — so
the `hi_res`-only path really does write a 4K reel.

With both on, a 2× crop is exactly 1920×1080 out of 3840×2160, so
`scale=-2:1080` is a no-op. Hence `MAX_ZOOM` 2.0: past that a 4K source can no
longer fill 1080p natively. A median face would want 2.3× to hit the 0.30
target, so wide shots land slightly short rather than going soft.

yt-dlp takes the best rendition ≤ the cap, so `hi_res` on a 1080p-only video
just yields 1080p; `min(ZOOM_OUTPUT_HEIGHT, source_height)` then keeps the reel
at 1080p rather than upscaling whole frames.

### Flow

`track_subject()` runs **only over surviving intervals**, sampling every
`ZOOM_SAMPLE_INTERVAL` (0.3s) on the **proxy** — normalised boxes carry to the
4K source exactly as timestamps do, so tracking never touches 4K.
`_best_match()` (was `_best_similarity`) now returns `(score, box)`; the box was
previously computed and thrown away. Per-clip **median** box, so one stray
bystander detection can't swing the framing. `plan_crops()` turns that into
normalised `(x, y, size)`; equal fractions of width and height preserve aspect.
`ZOOM_FACE_TOP_BIAS` 0.38 puts the face above centre for headroom.

### Verified 2026-07-27

- Crop region is pixel-correct: zoomed segment vs the expected crop region of
  the source = **0.09** mean abs diff (encoder noise); vs a full-frame
  downscale = **86.34**.
- Mixed reel (zoomed + un-zoomed segments) concats cleanly from a synthetic 4K
  source → 1920×1080, correct duration, audio intact. Same from a 1080p source
  (`crop=960:540` upscaled back to 1080p).
- All four toggle combinations round-trip through the API, and `_output_height()`
  returns `None` for both zoom-off rows so segments keep their source size.
- `track_subject()` on a real reel: wide shots measured 0.107–0.114 → 2× zoom;
  an existing close-up at 0.267 → correctly left alone.

### Known limits

- **Static crop per clip** — one rect from the clip median. A subject who walks
  across frame can drift out of it. Dynamic tracking was deliberately deferred;
  it needs temporal smoothing, a deadzone, and cut-snapping (a smoothed path
  would otherwise slowly *pan* across an interior scene cut, which looks worse
  than not zooming).
- Zoom decisions are per clip, never mid-clip — toggling framing inside a shot
  looks bad.
- 4K download + 4K decode per segment is the dominant cost; expect jobs to take
  substantially longer with zoom on.

---

## 13. Download naming & startup cleanup (added 2026-07-27)

### Unique download names

Every reel used to download as `facereel.mp4`, so a second download silently
overwrote the first. `process_job()` now returns a `filename` built by
`_output_filename()`: the **first 5 alphanumerics of the video title**, lowercased,
plus a `%Y%m%d-%H%M%S` timestamp — e.g. `ricka-20260727-151225.mp4`.

The title comes from `_video_title()`, a **separate metadata-only** yt-dlp call
(`--skip-download --print "%(title)s"`, which implies `--simulate`). It is
best-effort and returns `''` on any failure, so a title lookup can never fail a
job; the slug then falls back to `reel`. Titles that are entirely non-Latin
(CJK, emoji) also yield `reel`, since the slug keeps `[A-Za-z0-9]` only.

**Both ends must agree on the name.** A same-origin `<a download="...">`
attribute overrides the server's `Content-Disposition`, so setting `filename=`
on the `FileResponse` alone does nothing — `static/index.html` assigns
`$("download").download = r.filename` on completion, with a `facereel.mp4`
fallback for a stale page talking to a newer server.

Collisions need two jobs to finish in the same second, which the 409 single-job
lock makes impossible in practice. Add the job id to the slug if that ever
stops being true.

### Startup cleanup

`clean_jobs_dir()` removes every subdirectory of `storage/jobs/` and is wired to
a **FastAPI `lifespan` handler, deliberately not module scope** — importing
`app.py` (as any test does) must not delete the user's outputs. Keep it that
way. It only removes directories, leaves loose files alone, is idempotent, and
creates the folder if it is missing.

This is destructive by design: it makes disk state match the in-memory job dict,
which is empty at startup. Anyone who wants a reel to survive must download it
before restarting.

---

## 14. Containerisation & deployment (added 2026-09-05)

The app now runs continuously as a container on a home server (ACEMAGIC Mini PC
S1, Intel N95, under Proxmox, managed by Portainer). It is still the same
single-worker app — nothing about the pipeline changed.

**Delivery**: push to `main` → GitHub Actions builds `linux/amd64` → pushes
`ghcr.io/deshsa01/facereel:latest` **and** a `sha-<short>` tag. The package is
public, so the host pulls without logging in. Pin to a `sha-` tag in
`docker-compose.yml` to roll back. Docs-only pushes skip the build
(`paths-ignore`).

**On the host**, before first deploy:

```bash
sudo mkdir -p /opt/facereel/storage
sudo chown -R 1000:1000 /opt/facereel/storage   # container runs as uid 1000
```

Skipping the `chown` gives a `PermissionError` at startup instead of the
`Cleared N orphaned job folder(s)` line. Portainer stacks need an **absolute**
bind path — a relative one resolves inside the Portainer container, not on the
host.

### 14a. Three environment gaps that passed locally and failed in the container

These cost a full debugging cycle each. They are the reason constitution
Principle III exists.

**1. No JS runtime → hard 403 on every download.** YouTube signs media URLs
behind a JS player challenge. Bisected against a real video; all three are
required and any two alone still 403:

| yt-dlp | deno | `--remote-components ejs:github` | Result |
|---|---|---|---|
| 2026.6.9 | ✗ | ✗ | 403 |
| 2026.6.9 | ✓ | ✓ | 403 — old build picks the `android vr` client, now blocked |
| 2026.8.19 | ✓ | ✗ | challenge solving fails |
| 2026.8.19 | ✓ | ✓ | **works** (uses `visionos`) |

So: deno in the image, `--remote-components ejs:github` in `_ydl()`, and a
current yt-dlp. The Mac worked all along only because Homebrew had deno.
**The existing single retry in `_ydl()` does not help here** — that covers the
*transient* 403, which is a different failure.

**2. OpenCV cannot decode AV1 on Linux.** yt-dlp now serves AV1 by default.
OpenCV bundles *its own* FFmpeg, and in the Linux wheels its AV1 decoder is
hardware-only — the file opens and every read fails (`Failed to get pixel
format`), so `scan_video` sees zero frames. Installing system codecs does not
help; OpenCV does not use the system FFmpeg. The macOS wheel decodes AV1 in
software, which is why it only appeared once containerised.

Fix: the **proxy** (the file OpenCV scans) requests `[vcodec^=avc1]`. The
**source** is deliberately left unconstrained — YouTube publishes H.264 only up
to 1080p, so forcing avc1 there silently caps the 4K toggle (verified: the 2160
selector returns a 1080p rendition). Only the system ffmpeg touches the source.
`_decodable()` probes a real frame read because `isOpened()` returns True for a
file that cannot be read; `_transcode_for_analysis()` is the fallback when no
H.264 rendition exists at all.

**3. GHA cache export flakes.** `cache-to: type=gha` intermittently fails with
`not_found` *after* the image has already pushed, reddening a successful build.
Now `ignore-error=true`. If a build shows red, check whether the manifest was
pushed before assuming it failed.

### 14b. Deliberate constraints

- **One instance, one worker.** Job state is a module-level dict and the
  one-at-a-time rule is in-process. No `--workers`, no replicas.
- **`opencv-python-headless`** in the image (same `cv2` API, no GUI stack, so no
  `libGL`). The dev venv still has plain `opencv-python`.
- **`HOME=/home/app`** is set explicitly — Docker does not reliably derive it
  from `USER`, and deno caches under `$HOME`.
- **Encoding is still software libx264** (crf 18 / preset medium), unchanged.
  The N95 has QuickSync and `h264_vaapi` would be much faster, but it changes
  quality characteristics and needs a software fallback. **Deferred pending a
  real timing measurement** — that measurement has not been taken yet.

### 14c. Open question

LXC vs Docker was raised. Answer: no meaningful CPU difference — both are
namespaces + cgroups on the same kernel. The only reason to prefer an LXC is
that `/dev/dri` passthrough is trivial from one and painful from a VM, which
matters *only* if QuickSync encoding is pursued. Do not rewrite as a native LXC:
it would cost the pinned image, CI and rollback, and Debian trixie ships Python
3.13, not the 3.14 this is tested on.

---

## 15. Next up: the reel archive (specced 2026-09-05, NOT built)

**Everything needed to start implementing is in `specs/001-reel-archive/`.**
Read `spec.md` then `plan.md`, and work `tasks.md` in order.

### The problem

A finished reel lives in `storage/jobs/<id>/output.mp4` and the job record exists
only in memory, so `clean_jobs_dir()` destroys every past reel at startup (§13).
That was a fair trade for a hand-started local tool. It is data loss now that the
app runs continuously and restarts on every redeploy.

### The design in one paragraph

A sibling `storage/archive/` that the startup wipe never touches, holding one
self-contained directory per reel — `output.mp4`, `thumb.jpg`, the reference
screenshot, and a `reel.json` sidecar. A new `archive.py` owns it; `app.py` gains
list/media/delete endpoints and serves `static/archive.html`. `pipeline.py` is
untouched.

### Decisions already settled with the user — do not relitigate

- **Retention is unlimited.** Nothing is ever auto-deleted. Total archive size is
  displayed instead, as the agreed compensating control.
- **Thumbnail grid**, using a poster frame from the reel (not the uploaded face
  image) — a title alone does not say *which person* a reel is of.
- **Stored per reel**: the stats `process_job()` already returns, the five tuning
  values, the source URL, the reference screenshot, and a creation timestamp.
- **Deletion is permanent.** No recycle bin, no undo; confirmation is the only
  safeguard.
- **No migration.** Existing reels in job directories are lost at the next
  restart, exactly as they would be today.

### Two things to get right, or the feature is worse than not having it

1. **Validate the id before building any path.** `^[0-9a-f]{12}$`, in
   `archive.py` so no endpoint can skip it. Every archive endpoint builds a
   filesystem path from a URL segment and one of them calls `shutil.rmtree`.
   `quickstart.md` step 5 tests traversal — **run it before trusting the delete
   endpoint**.
2. **Assemble entries in `.tmp-<id>/` and `os.rename` into place.** A rename is
   atomic, so a half-written entry is never visible. Without it an interrupted
   archive leaves an entry that lists but will not play — discovered only later,
   when the reel is already unrecoverable. Write `reel.json` last.

### Sequence

`tasks.md` has 33 tasks in six phases. **US1 alone (T007–T013) is the MVP** — it
ends the data loss with no UI at all, and is worth landing and verifying on its
own. US2 (browse/play) then US3 (delete) follow, in that order because a
destructive endpoint should not exist before there is a tested listing to confirm
it acts on the right entry.

Verification is `quickstart.md`. The step that actually matters is the
**container redeploy test** (its step 6), not just a local restart — redeploy is
what happens on every new image.

### Working with spec-kit

Installed at `.specify/`, with skills in `.claude/skills/` as `/speckit-*`
(`-specify`, `-plan`, `-tasks`, `-implement`, `-clarify`, `-analyze`,
`-checklist`, `-converge`). **A session must be started *after* installation for
the skills to be invocable** — they were installed mid-session and could not be
called in that session; the artifacts were produced by following each skill's
documented steps by hand instead. A fresh session can just run
`/speckit-implement`.

`create-new-feature.sh` does **not** create or switch git branches in this
version; it only makes `specs/NNN-name/`. `.specify/feature.json` is the
machine-local pointer to the active feature and is gitignored by spec-kit.

**Caveat**: `.gitignore` excludes `.claude/`, so the spec-kit skills are
untracked and a fresh clone will not have them (re-run `specify init`, or change
the ignore to `.claude/*` plus `!.claude/skills/` — git cannot re-include inside
an excluded *directory*, so the current single-line pattern will not work).

### Constitution

`.specify/memory/constitution.md`, v1.0.0, ratified 2026-09-05. Five principles
derived from conventions already in this repo, each citing its evidence. It
deliberately does **not** mandate test-first: there is no test suite, and an
unmet gate is just something to route around. Plans carry a Constitution Check;
`specs/001-reel-archive/plan.md` passes all five.
