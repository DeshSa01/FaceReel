# Supercut

Formerly FaceReel. Web app that takes a YouTube URL plus a screenshot of a
person from that video, finds every moment the person appears, and stitches
those clips into one continuous playable video.

## Look and feel

Every page shares one header (the logo, Sessions, Archive) and one design
system: `static/css/supercut.css` holds every colour, size and timing, and
`static/js/shell.js` the shared behaviour. There is no build step and no
front-end framework; the pages are plain HTML served as they are.

- **Theme**: the sun/moon/monitor button at the right of the header picks
  Light, Dark or System. System, the default, follows the operating system,
  including when it switches at sunset. The choice is remembered per browser
  (not per device or account), and other open tabs follow it.
- **Browsers**: current Safari (17.5+, macOS and iOS), Chrome or Edge (123+)
  and Firefox (120+). The themes rely on CSS `light-dark()`; an older browser
  gets the light theme and otherwise works.
- **Home screen**: on iOS, Share → Add to Home Screen gives a Supercut icon that
  opens without browser chrome. On Android, Chrome only installs a full app
  from an HTTPS address; over this app's plain-HTTP LAN address it adds a
  shortcut that opens in a browser tab.
- **Icons**: the PNG icons in `static/brand/` are rendered from the SVGs there
  by `tools/render-icons.sh` (headless Chrome, run by hand). Re-run it and
  commit the PNGs whenever the logo changes.

## Run locally

```bash
.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8765
```

Then open http://127.0.0.1:8765. The first page lists the **sessions** that
are running and offers to start a new one. The quickest start is to **paste a
YouTube link** into the field at the top and press Start: that creates a
session and opens it with the link already filled in, ready for the
screenshot.

On the session page the screenshot can be **pasted** (⌘V / Ctrl+V, anywhere on
the page, even with the cursor in the link field), **dropped** onto the page,
or chosen with the file picker. It shows as a round "Looking for" chip. A
recognised YouTube link shows its thumbnail and title before you add it;
thumbnails load straight from YouTube, titles through the app's
`/api/youtube/preview`. Any other link is flagged but still accepted, exactly
as before. The clip fine-tuning sliders live under **Advanced**, which opens
by itself when the values aren't the defaults.

A session is a queue of up to **10 videos**. Each video gets its own YouTube
link, screenshot of the person, and settings. After the first one, the form
keeps the previous video's screenshot and settings, so adding another video of
the same person takes just a link. The first video starts processing as soon
as it's added; later ones wait their turn. Every session, from every browser,
shares one queue, and the machine processes **one video at a time, oldest
session first**. A session started earlier gets all of its videos done, and
its joined reel made, before a later session's videos start. Within a session,
videos run in the order they were added. The video currently processing is
never interrupted. A waiting video's row on the session page says when it is
waiting on another session.

**A session finishes on its own once its queue is empty**, meaning nothing is
waiting and nothing is processing. It then joins every successful video's reel,
in order, into one video for the whole session. So **add the next video while
the current one is still running**. The session page warns you while its last
video is processing. A video added after a session has finished goes into a
new session.

The joined video is identified by the session id. It shows on the session page
(`/session/<id>`), in the archive with a **Session** badge, and at
`/api/sessions/<id>/output`. Each video's own reel is archived as well, so if
the join fails, nothing is lost. A video that fails (for example, the person
isn't found) is skipped, and the session's summary says why. Losing the
connection to YouTube is different: the video goes back in line and the whole
queue pauses, then retries after 30 s, 1 m, 2 m, and so on up to 10 m. It gives
up after eight retries, about 45 minutes. The bar and the session page show
the countdown, and sessions stay open while they wait.

Videos that did fail can be retried together: **Retry failed videos** on the
session page, or on the session's reel in the archive. That reopens the
session, puts the failed videos back in the queue, and once they finish,
joins the session again from all its clips. The new reel replaces the old one
under the same session id. A waiting video
can be removed before it starts. A session that never got a video can be
discarded.

Sessions live on the server. Open the app from any browser or device, join a
running session, and you'll see the same queue. Progress also shows in a bar
pinned to the bottom of every page, naming the session and the video ("video 2
of 5"). The bar announces when a session's joined reel is ready.

While a video processes, its row shows each stage (download, scan, refine,
frame when zoom is on, stitch) with the elapsed time. A tab in the background
still shows progress: its title starts with the percentage ("42% · Scanning ·
…") and, in browsers that redraw favicons (not Safari), the icon gains a
progress ring. To keep that current, **a hidden tab checks every 10 seconds**
instead of not at all; browsers slow long-hidden tabs to about once a minute
regardless. When a session's reel is ready, its page shows it large with a
short celebration, once per finished reel.

**Notifications, the share sheet and one-click copy need HTTPS** (or
`localhost`). Browsers only grant those to secure origins, and this app is
served over plain HTTP on the LAN, so on the deployment there is no
notification offer and no Share button; Copy link still works through a
fallback, and the tab title is the background signal. Putting the app behind
HTTPS (a reverse proxy, or Tailscale's HTTPS for the tailnet name) turns them
on with no code change. On `localhost` they all work, so check them against the
deployment, not just the dev machine.

**Sessions survive restarts and redeploys.** If the app restarts mid-session,
the video that was processing starts over from the beginning (its partial
progress is lost), and the waiting videos carry on in order. Nothing needs
redoing by hand.

## Run with Docker

Every push to `main` builds a `linux/amd64` image and pushes it to
`ghcr.io/deshsa01/facereel:latest` (`.github/workflows/docker.yml`). The
package is public, so the host pulls it without logging in.

**First, on the host**, create the storage directory and give it to uid 1000 —
the user the container runs as:

```bash
sudo mkdir -p /opt/facereel/storage
sudo chown -R 1000:1000 /opt/facereel/storage
```

Do this *before* deploying. If the path doesn't exist, Docker creates it owned
by root and the container can't write it.

**Deploying with Portainer** (how the nucbox runs it): Stacks -> Add stack ->
paste `docker-compose.yml` into the web editor -> Deploy. Override
`STORAGE_PATH` or `TZ` under "Environment variables" if the defaults don't
suit. Take a new build with the stack's **Pull and redeploy**.

**Or without Portainer:**

```bash
docker compose up -d
docker compose pull && docker compose up -d   # to take a new build
```

Either way, open `http://<host>:8765`.

Notes:

- **Run exactly one instance, one worker.** A single runner thread in the
  process is the only consumer of the session queue, and the only writer of
  each `session.json`. A second worker or replica would process two videos at
  once and race on those files.
- The storage path is bind-mounted, so job scratch is visible on the host —
  but it is still wiped on every startup, same as a local run. A healthy start
  logs `Cleared N orphaned job folder(s)`; a `PermissionError` there means the
  `chown` above was skipped.
- The bind mount uses an **absolute** path. A relative one (`./storage`) in a
  Portainer stack resolves against the Portainer container's filesystem rather
  than the host's.
- Encoding is software libx264 (crf 18 / preset medium), unchanged from local.
  On a low-power host this is the slow part of a job.
- Pin `image:` to a `sha-<short>` tag instead of `latest` to roll back.

### Bumping yt-dlp

YouTube changes break yt-dlp periodically. It is pinned in its own file,
`requirements-ytdlp.txt`, installed as the last layer of the image: edit the
version there, push, and the rebuild is seconds rather than a full reinstall.

## Requirements

Running locally:

- `ffmpeg` on PATH (installed via Homebrew)
- **`deno` on PATH** (`brew install deno`). YouTube signs media URLs behind a
  JS player challenge; without a JS runtime every download fails with a hard
  403. deno is the only runtime yt-dlp enables by default. The pipeline also
  passes `--remote-components ejs:github` so yt-dlp fetches the solver scripts
  it needs — a runtime is necessary but not sufficient on its own.
- Python venv in `.venv` with the packages in `requirements.txt` (plus
  `requirements-ytdlp.txt`). The venv uses `opencv-python`; the image uses
  `opencv-python-headless`, which is the same `cv2` API without the GUI stack.
- Face models in `models/` (YuNet detector + SFace recognizer, from the
  [OpenCV model zoo](https://github.com/opencv/opencv_zoo))

yt-dlp goes stale quickly against YouTube — a version a couple of months old
fails with a 403 even with deno present. Keep `.venv` in step with
`requirements-ytdlp.txt`: `.venv/bin/pip install -U yt-dlp`.

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
A session's joined reel downloads as `supercut-session-<id>.mp4`; ones made
before the rename keep their original `facereel-session-<id>.mp4` name.

**`storage/jobs/` is scratch.** Each video's folder is deleted as soon as that
video finishes or fails, and so is a session join's working folder
(`storage/jobs/join-<id>/`). Anything still there at startup was interrupted,
and is wiped. A finished reel never lives there; it's moved to the archive
first (see below).

## Sessions on disk

`storage/sessions/<id>/` holds one session: `session.json` (the queue, each
video's state and settings) and `screenshots/`. It is written on every state
change and survives restarts. This is what lets a queue resume after a
redeploy. Nothing deletes it automatically. The only way it is removed is
discarding a session that never had a video, which is a button on the session
page and removes only that session's folder.

**One automatic deletion runs at startup:** half-written archive folders named
`storage/archive/.tmp-<id>/`, which a crash in the middle of archiving a reel
leaves behind. They are never a complete reel (an entry only becomes visible
when it is renamed into place), and leaving one would make the retried video
fail.

**A second automatic cleanup** belongs to retries. When a session's reel is
replaced, the old one is briefly parked as `storage/archive/.old-<id>/`. If the
app stops at that moment, the next startup puts the old reel back (if its
replacement never landed) or deletes it (if it did).

## The archive

Every reel that finishes generating is moved into `storage/archive/<id>/`
along with a poster frame, the reference screenshot, and a `reel.json`
sidecar of its stats and settings. Unlike `storage/jobs/`, **the archive is
never wiped, by anyone, automatically** — it survives restarts and
redeployments, and it lives on the same bind-mounted volume the rest of
`storage/` uses, so it survives a container being replaced entirely, not just
restarted.

Browse it at `/archive` (linked from every page's header): a thumbnail grid
with in-page playback, download, and deletion. Search narrows the grid by
title as you type; filter to session reels or single reels, and sort by
newest, oldest, longest or largest (the filter and sort are remembered per
browser; the search isn't). Hovering or focusing a card plays a muted preview
of the reel's first few seconds. In the viewer, ← and → step through the
reels in the current order and Escape closes it. The meter at the top shows
the archive's size against the drive it lives on, and turns amber when less
than 10% of the drive is free. The home page shows the six newest reels.

**Clip navigation**: under a reel's player, a strip shows every clip as a
segment sized to its length, with the current one lit. Click a segment to
jump to it; the ⏮ ⏭ buttons (or `[` and `]` while the player has focus) step
between clips. A session reel's strip is tinted per source video and names
the video under the pointer. Only reels made from this version on have it:
the clip positions are recorded when the reel is cut (each cut segment's
duration is measured, so the marks land exactly), and older reels play as
they always did. In a session that joins an older reel with newer ones, the
older one shows as a single stretch with its title. **Deletion is
permanent** — there is no undo, no recycle bin, and an in-page confirmation
naming the reel is the only safeguard. A failed delete says so in a message at
the bottom of the page; the reel stays. Because nothing is ever deleted automatically,
the archive only grows; the page shows the running total size on disk so
that filling the drive is a visible risk rather than a silent one, and it's
on you to delete old reels if space gets tight.

If archiving fails in the container with a permission error, the bind mount
is not writable by uid 1000 — the same failure mode already documented above
for `storage/jobs/`; the fix is the same `chown -R 1000:1000` step.
