# Quickstart: Validating 004 UI Overhaul

Each step is tagged with where it **must** run (constitution Principle III):

- **[local]**: the dev machine, `http://127.0.0.1:8765`. This is a secure origin.
- **[deploy]**: the container on the nucbox, `http://<host>:8765` from another device on
  the LAN. This is **not** a secure origin.
- **[phone]**: a real phone on the LAN, pointed at the deployment.

Several features behave differently in [local] and [deploy] **by design** (research D6,
D9). A step that passes locally proves nothing about those features in production.

## Prerequisites

- **[local]** Start the app: `.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8765`.
  Restart it after any Python change; pages and static assets reload live.
- **[deploy]** The pushed build is pulled and redeployed in Portainer ("Pull and
  redeploy").
- At least one finished session reel and one single reel in the archive, ideally with
  30 or more reels for the archive checks. Reels made **before** this deploy are needed
  too, for the backward-compatibility checks.
- Two browsers: one Chromium-based, plus Safari.

## 1. Tokens and contrast

1. **[local]** Run `python3 specs/004-ui-overhaul/contrast.py`.
   **Expect**: exit 0, with every line `ok`.
2. **[local]** Run `grep -nE '#[0-9a-fA-F]{3,8}\b' static/css/supercut.css` and check that
   the hits are only in the token block at the top of the file, and
   `grep -n 'style>' static/*.html` for page-level styles.
   **Expect**: no colour literals outside the token block, and no page-level `<style>`
   that redefines a shared component (FR-007).

## 2. Identity (User Story 1)

1. **[local]** Open `/`, `/session/<id>` and `/archive`.
   **Expect**: the same header on each, with the current nav item marked, and tab titles
   "Sessions · Supercut", "<session> · Supercut" and "Archive · Supercut".
2. **[local]** Open 12 or more other tabs. Find Supercut by favicon alone, with the
   browser in light appearance and then in dark (SC-001).
3. **[local]** `curl -sI http://127.0.0.1:8765/favicon.ico` and `/manifest.webmanifest`.
   **Expect**: `200`, with `image/png` and `application/manifest+json` respectively.
4. **[local]** `curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8765/static/index.html`
   and `.../static/..%2Fapp.py`.
   **Expect**: `404` for both (allow-list, research D14).
5. **[phone]** iOS Safari → Share → Add to Home Screen.
   **Expect**: the Supercut icon and label, and it opens standalone.
   Android Chrome → Add to Home screen.
   **Expect**: the Supercut icon. It opens in a browser tab over HTTP, which is the
   documented limitation, not a failure (research D6).
6. **[deploy]** Finish a session and download its reel.
   **Expect**: `supercut-session-<id>.mp4`. Download an old session reel.
   **Expect**: its original stored name.

## 3. Theme (User Story 3)

1. **[local]** With the OS in light, choose Dark. Reload 20 times and navigate between
   all three pages, recording the screen.
   **Expect**: zero light frames when stepped through frame by frame (SC-003). Repeat
   with the OS dark and Light chosen.
2. **[local]** Choose System, then toggle the OS appearance.
   **Expect**: the page follows within a second, with no reload.
3. **[local]** Open two tabs and change the theme in one.
   **Expect**: the other follows.
4. **[local]** Open a private window.
   **Expect**: it follows the OS, the control works for that page, and there are no
   console errors.
5. **[local]** In Dark, play a reel.
   **Expect**: no bright border or halo around the video, and native controls are dark.

## 4. Adding videos (User Story 4)

1. **[local]** With a YouTube link and a screenshot on the clipboard: on `/`, paste the
   link and press Enter, then paste the image (⌘V), then submit.
   **Expect**: a session is created and the video queued in 3 actions, in under 15 s
   (SC-004).
2. **[local]** Drag an image onto the dropzone.
   **Expect**: a face chip labelled "Looking for". Drop a `.txt` file.
   **Expect**: an error message, and the chip is unchanged. Drop two images.
   **Expect**: the first is used, and a note says so.
3. **[local]** Paste an image while the caret is in the URL field.
   **Expect**: the screenshot changes and the URL text is untouched.
4. **[deploy]** Type a link.
   **Expect**: a thumbnail, then the title, within about a second. Run
   `curl 'http://<host>:8765/api/youtube/preview?url=https://youtu.be/<id>'` from the LAN.
   **Expect**: `200` with a title. This proves the container's route to YouTube oEmbed
   (research D7).
5. **[local]** Enter a link that isn't YouTube.
   **Expect**: an inline hint, and submit still sends it. The server responds exactly as
   it does today.
6. **[local]** Add a second video.
   **Expect**: the chip says "Same as video 1", and Advanced opens on its own if the
   values differ from the defaults.

## 5. Progress and the reveal (User Story 5)

1. **[local]** Add a video with zoom on.
   **Expect**: the stage track shows download → scan → refine → frame → stitch, with the
   current stage highlighted, earlier stages ticked, and the elapsed time counting. With
   zoom off there is no "frame" stage.
2. **[deploy]** Switch to another tab for 30 s.
   **Expect**: the tab title reads "NN% · Stage · Supercut" and moves at least every
   ~10 s. In Chromium the favicon shows a ring.
3. **[deploy]** Disconnect the host's uplink briefly, or wait for a real network-wait
   pause.
   **Expect**: the paused style with a countdown, distinct from failure.
4. **[local]** Let a session finish while on its page.
   **Expect**: the celebration plays once (≤ 1.6 s) and the presenter shows its stats.
   Reload.
   **Expect**: no replay. Retry a failed video and let it rebuild.
   **Expect**: a new celebration, and the bar's "ready" notice reappears. The latter was
   broken before this feature (research D12).
5. **[local]** Turn on Reduce Motion in the OS and repeat step 4.
   **Expect**: no particles, a simple fade, and no animated stage track.
6. **[local]** Notifications: on a first session, the in-page offer appears. Accept it,
   hide the tab, and let a session finish.
   **Expect**: a system notification. Clicking it opens the session.
7. **[deploy]** Notifications.
   **Expect**: **no** offer is shown and nothing errors, because HTTP is not a secure
   origin (research D9). Copy link still works through the fallback. Share is hidden.
8. **[local]** Upgrade check: dismiss a terminal notice on the pre-upgrade build, then
   deploy this one.
   **Expect**: that notice does not reappear (key migration, research D12).

## 6. Archive (User Story 6)

1. **[local]** With 30 or more reels: search part of a title.
   **Expect**: the grid narrows as you type. Choose Sessions, then sort by Largest. Reload.
   **Expect**: filter and sort are kept, and the search is cleared.
2. **[local]** Hover a card.
   **Expect**: after ~250 ms a muted preview plays, and it stops on leave. Tab to a card
   with the keyboard.
   **Expect**: the same behaviour. Under Reduce Motion: no preview.
3. **[local]** Open a reel.
   **Expect**: ← and → step through the current filtered order, and Esc closes.
4. **[local]** Delete a reel.
   **Expect**: an in-page confirmation naming it, the card animating out, the meter
   updating, and a toast stating the space freed. Stop the server and delete again.
   **Expect**: an error toast, not `alert()`.
5. **[local]** Search for nonsense.
   **Expect**: "Nothing matches" with a Clear button.
6. **[local]** Time finding a named reel among 50 or more (SC-009, under 10 s).

## 7. Clip navigation (User Story 7)

1. **[deploy]** Make a new single reel with several clips and open it.
   **Expect**: the number of strip segments equals `clip_count`. `]` lands on each segment
   start, and the current segment highlights during playback.
2. **[deploy]** Make a new session reel of 2 or more videos, including one whose reel was
   made **before** this deploy.
   **Expect**: segments are tinted per video. The old video appears as one unbroken
   stretch labelled with its title, and hover names each video.
3. **[deploy]** Open a reel made before this deploy.
   **Expect**: no strip, and normal playback (FR-043).
4. **[deploy]** Time `cut_and_stitch`'s probe step for a reel of about 50 clips. Record the
   figure in the code comment (research D13, Principle II).
5. **[local]** Check that the last clip's `end` matches the reel's duration:
   `jq '.clips[-1].end, .output_duration' storage/archive/<id>/reel.json`.
   **Expect**: they agree to within 0.05 s.

## 8. Parity, accessibility and responsiveness

1. **[deploy]** Walk through every capability listed in spec FR-044 on the new design and
   tick each one off. **Expect**: no regressions (SC-005).
2. **[local]** Unplug the mouse and do the whole User Story 2 independent test by
   keyboard. **Expect**: a focus ring is always visible (FR-010).
3. **[local]** Run VoiceOver while a video processes.
   **Expect**: an announcement on each stage change, and none per percentage point
   (FR-015).
4. **[phone]** Check every page at 360px.
   **Expect**: no horizontal scroll. The pinned bar never covers the submit button, and a
   10-video queue is readable (SC-006).
5. **[deploy]** Time each page to meaningful content on the LAN (SC-007, under 1 s), and
   compare with the pre-upgrade build.
6. **[local]** `grep -nE '\balert\(|\bconfirm\(|\bprompt\(' static/` should return nothing
   (FR-013).
