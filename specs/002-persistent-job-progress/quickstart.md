# Phase 1 Quickstart: Verifying Persistent Job Progress

Most of this feature cannot be verified by reading code, because the two things that matter are events the code cannot observe: a browser window actually closing, and a container actually being replaced. **Steps 4 and 8 are the ones that decide whether the feature works.** Everything else is setup for them.

You will need a real reel in flight for most steps, and a reel takes minutes — use a long enough video that you have time to navigate while it runs. Keep one browser dev-tools Network tab open; several assertions are about requests that should or should not be happening.

## Local (fast loop)

```bash
.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8765
```

### 1. The endpoint answers with nothing running (FR-002)

Before submitting anything:

```bash
curl -s localhost:8765/api/jobs/active | python3 -m json.tool
```

Must be `{"job": null}` with a **200**, not a 404. Open `/` — no bar, and no blank strip reserved at the bottom (FR-011).

### 2. The bar appears and tracks (FR-003, FR-004, FR-018)

Submit a reel. The bottom bar appears on the generator page, naming the current stage in words ("Downloading video", "Scanning for the person"), not a raw stage key. Meanwhile:

```bash
watch -n1 'curl -s localhost:8765/api/jobs/active | python3 -c "
import json,sys; j=json.load(sys.stdin)[\"job\"]
print(j[\"status\"], j[\"stage\"], j[\"progress\"], j[\"message\"])"'
```

The bar must not lag this by more than two seconds. In the Network tab, confirm **one** request per second — if you see two, `index.html`'s old `poll()` was not deleted (research D10).

### 3. Navigating away (Story 2 — FR-005, FR-006)

With the reel still running, click **View archived reels**. Then:

- The bar is present at the bottom of the archive page, still advancing.
- Open an archived reel and play it through. Playback works, and progress keeps moving (FR-006). Both may be slower — the machine is encoding.
- Scroll to the bottom of the grid. The last row of reels must be fully visible and clickable, not underneath the bar (FR-016).
- Go back to the generator. Same reel, same progress, and the submit button is disabled with a visible reason (FR-014).
- Open `/archive` directly in a fresh tab without visiting `/` first — the bar is there too.

Confirm the reel completes normally despite all of this (SC-001).

### 4. Closing the browser — the point of the feature (Story 1, SC-002)

Start a reel. **Quit the browser entirely** — not just the tab, and not a reload. Wait a minute or two. Reopen and go to `http://127.0.0.1:8765/`.

The bar must be there within two seconds of the page appearing, showing progress that has *advanced* while the browser was shut, and continuing to advance. Cross-check the figure against `curl` as in step 2.

Then reload several times in a row. Progress must never restart at zero or move backwards (Story 1, scenario 2) — if it does, something is caching client-side, which FR-007 forbids.

### 5. Two windows agree (FR-013)

With a reel running, open the generator and the archive in two windows side by side. Both show the same reel at the same progress. Now leave one window hidden behind the other for thirty seconds and check the Network tab of the hidden one: **it should have stopped polling entirely** (research D2). Bring it forward — it must catch up immediately, not on the next tick.

### 6. Completion and acknowledgement (Story 3 — FR-008, FR-010)

Let a reel finish while you are on the **archive** page. The bar reports completion and offers a link. Click it: that reel's player opens — including the case where you were already on the archive page, which needs `hashchange` handling, not just load handling (research D9).

Dismiss the notice, then reload. It must not come back (FR-010). Let a reel finish while you are on the **generator** page instead: the existing result card must still appear with its stats line and working download link, exactly as before this feature.

### 7. Failure is reported (FR-009)

Submit a deliberately broken URL (a private or deleted video). The bar shows the failure and the reason on whichever page you are on. Dismiss it and submit a valid reel — it is accepted and the bar tracks from zero.

### 8. Interruption — the honest-failure test (FR-012, SC-006)

Start a reel and let it reach a visible percentage. Then **stop the server** (Ctrl-C) and start it again.

```bash
curl -s localhost:8765/api/jobs/active   # {"job": null} — the record died with the process
```

With the page still open, within a few seconds the bar must say the reel **did not finish**. It must not sit frozen at its last percentage, and it must not silently disappear — a bar that vanishes reads as "finished" and is the failure this requirement exists to prevent.

Reload the page. Still reported (or dismissible), never a phantom reel in progress.

### 9. Losing contact (FR-015)

Start a reel, then stop the server **without** restarting it. After roughly two seconds the bar marks its figure as no longer live. Start the server again — the bar must resume live updates **on its own, with no reload**. Because the record died with the process, this correctly lands in step 8's interrupted state; that is the right outcome, not a bug.

### 10. The concurrency fix (research D6)

The bug this closes is timing-dependent, so drive it rather than hoping:

```bash
# hammer both endpoints across a reel's completion moment
while true; do
  curl -s -o /dev/null -w "%{http_code} " localhost:8765/api/jobs/active
  curl -s -o /dev/null -w "%{http_code} " localhost:8765/api/jobs/<job-id>
done
```

Run this from before submission until after completion. Every code must be `200`. A `500`, with `RuntimeError: dictionary changed size during iteration` in the server log, means `output_path` was not seeded at creation.

## Container (the environment that ships)

Constitution Principle III: the container is the source of truth. Build and run the image as the README describes, then repeat **steps 2, 3, 4 and 6** against it — they exercise the browser behaviour, which is where a stale-asset problem would show up.

### 11. Stale assets after a redeploy (research D3)

```bash
curl -sI localhost:<port>/static/progress.js | grep -i cache-control
```

Must be `no-cache`. Then change something visible in `progress.js`, rebuild, redeploy, and hard-*less* reload (ordinary reload, no cache bypass) — the change must be live. If it is not, the bar will silently keep running old code against a new `app.py` after every deploy.

### 12. Redeploy mid-reel — the production case for FR-012

**This is the step that matters most**, because it is what actually happens: CI publishes an image on every push to `main`, and a redeploy kills an in-flight reel.

Start a reel in the container, wait for a visible percentage, then redeploy the container while it runs, with the browser page left open. Within five seconds of the container coming back, the bar must report the reel did not finish (SC-006). Confirm `storage/archive/` gained no entry for it — an interrupted reel is not half-archived — and that submitting a new reel afterwards works normally.

## What "done" looks like

| Check | Requirement |
|---|---|
| Reel completes while you navigate, watch archived reels, and close the browser | SC-001 |
| Live progress visible within 2s of reopening, never stale or reset | SC-002, FR-007 |
| Bar present on both pages, covering nothing, absent when idle | SC-003, FR-003, FR-011, FR-016 |
| Archived reel plays within ~3s while a reel is processing | SC-004 |
| No finished reel goes unreported — announced, or in the archive on return | SC-005 |
| Interrupted reel reported within 5s; never a frozen bar | SC-006, FR-012 |
| Submit → watching an old reel in under 10s and 3 clicks | SC-007 |
| No 500s across a completion boundary under continuous polling | research D6 |
