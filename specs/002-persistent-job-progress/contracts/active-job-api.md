# Phase 1 Contract: Active Job API and the Shared Indicator

All paths are relative to the app root. No authentication — the app has none and runs on a trusted home network (spec Assumptions).

**This contract assumes a single process.** `GET /api/jobs/active` answers from the in-memory `jobs` dict, so under a second uvicorn worker it would answer from whichever process took the request and be wrong roughly half the time. That constraint already governs `POST /api/jobs`'s 409 and `GET /api/jobs/{id}`; this feature makes the entire indicator depend on it.

## Existing endpoints — unchanged

| Method | Path | Note |
|---|---|---|
| POST | `/api/jobs` | Unchanged, including the 409 on concurrent submission. The indicator now makes the refusal predictable rather than surprising (FR-014). |
| GET | `/api/jobs/{job_id}` | Response unchanged. Internally no longer raises `RuntimeError` when polled at the moment of completion (research D6). |
| GET | `/api/jobs/{job_id}/output` | Unchanged. |
| GET | `/`, `/archive` | Unchanged behaviour; both pages gain one `<script>` tag. |
| GET, DELETE | `/api/archive/...` | Entirely unchanged. |

---

## `GET /api/jobs/active` — new

Reports the reel currently being processed, or the most recently finished one. Takes no parameters and requires the caller to remember nothing (FR-002).

**Selection**: the `processing` record if one exists; otherwise the most recently created record in any state; otherwise `null`.

**200 — a reel is being processed**

```json
{
  "job": {
    "id": "a1b2c3d4e5f6",
    "status": "processing",
    "stage": "scan",
    "progress": 41.5,
    "message": "Scanning 00:03:12 of 00:07:40...",
    "result": null,
    "tuning": {"lead_in": 0.15, "boundary_reach": 0.6, "clip_gap": 0.6, "zoom": false, "hi_res": false}
  }
}
```

**200 — the most recent reel finished**

```json
{
  "job": {
    "id": "a1b2c3d4e5f6",
    "status": "done",
    "stage": "done",
    "progress": 100,
    "message": "Done!",
    "result": {"filename": "facereel.mp4", "clip_count": 25, "output_duration": 134.2,
               "source_duration": 212.0, "resolution": "1920x1080", "zoomed_clips": 0},
    "tuning": {"lead_in": 0.15, "boundary_reach": 0.6, "clip_gap": 0.6, "zoom": false, "hi_res": false}
  }
}
```

**200 — the most recent reel failed**

```json
{
  "job": {
    "id": "a1b2c3d4e5f6",
    "status": "error",
    "stage": "download",
    "progress": 12.0,
    "message": "Could not download the video: HTTP Error 403: Forbidden",
    "result": null,
    "tuning": {"lead_in": 0.0, "boundary_reach": 0.0, "clip_gap": 0.0, "zoom": false, "hi_res": false}
  }
}
```

**200 — nothing known** (fresh start, or every record lost to a restart)

```json
{ "job": null }
```

### Guarantees

- **Never 404.** Absence is `{"job": null}` with a 200, because "nothing is being processed" is a normal answer, not an error. A client that got a 404 could not distinguish it from a broken route.
- **`output_path` is never present.** It is a server filesystem path, excluded exactly as `get_job` already excludes it.
- **Reflects the truth at the moment of the request.** No caching layer, no staleness. Progress is read from the live record.
- **Safe to call at any rate.** Read-only, no locking, no allocation beyond the response. A dict copy is safe because the record's key set is fixed at creation (research D6).
- **`{"job": null}` is not proof a reel never existed.** After a restart the record is gone with the process. Distinguishing "never started" from "was interrupted" is the client's job, using its own `facereel.watching` value (research D4).

### Route ordering — load-bearing

`GET /api/jobs/active` MUST be declared **above** `GET /api/jobs/{job_id}` in `app.py`. FastAPI matches in declaration order; declared after, `active` is captured as a `job_id` and the endpoint answers 404 forever — a silent failure in which the indicator simply never appears. Job ids are `^[0-9a-f]{12}$`, so `active` can never be a real id; only the ordering matters. This needs a comment at the declaration site.

---

## `GET /static/progress.js` — new

Serves the shared indicator.

- **200** — `static/progress.js`, `Content-Type: application/javascript`, **`Cache-Control: no-cache`**.

The cache header is required, not incidental. `FileResponse` sends no cache headers, so browsers heuristically cache and serve a stale copy across restarts — the reason `/` and `/archive` already set it. A stale `progress.js` against a current `app.py` yields a bar that silently stops working after a redeploy, which is harder to diagnose than a stale page because nothing looks wrong.

Served by an explicit route rather than a `StaticFiles` mount: the mount sets its own validators instead of `no-cache`, reintroducing the problem, and exposes the whole directory where the current code exposes named files deliberately (research D3).

---

## Page contract for the indicator

`progress.js` is drop-in: one `<script src="/static/progress.js">` before `</body>` is the whole integration. It injects its own markup and styles and requires no markup from the host page.

**What it expects of a page**

- Nothing mandatory. It reads the `--card`, `--border`, `--accent`, `--muted` and `--text` custom properties both pages define, with literal fallbacks so it still renders correctly without them.
- It manages `document.body.style.paddingBottom` while visible, so a page must not also drive that property.

**What it offers a page** — an optional hook so a page can react to the same updates rather than polling on its own:

```js
window.FaceReelProgress.subscribe(job => { /* job, or null */ });
```

Used by `index.html` to drive its progress card, its submit button (FR-014) and its result card, replacing the deleted `poll()`/`finish()`. A page that ignores the hook still gets the bar.

**Where the notice leads** — the completion notice links to `/archive#<id>`. The archive entry id *is* the job id (`archive_job(job_id, ...)` writes `"id": job_id`), so this addresses the archived reel with nothing new plumbed through. `archive.html` MUST open that reel's player both on load with a matching hash and on `hashchange`, so that clicking the notice while already on the archive page works.

---

## Requirements traceability

| Requirement | Where it is met |
|---|---|
| FR-001 | Already true — `_worker` is a daemon thread that never consults the client. Verified, not built. |
| FR-002 | `GET /api/jobs/active`, no client-supplied id |
| FR-003, FR-011, FR-016 | `progress.js` injected bar; body padding managed while visible |
| FR-004, FR-013 | 1s poll while visible, immediate catch-up on `visibilitychange` |
| FR-005, FR-006 | No change needed — verified in `quickstart.md`, not implemented |
| FR-007 | No progress cached client-side; first render follows the first response |
| FR-008 | Completion notice → `/archive#<id>` + `hashchange` handling |
| FR-009 | `message` rendered on the `error` state |
| FR-010 | `facereel.acknowledged` in `localStorage` |
| FR-012 | `facereel.watching` compared against `{"job": null}` |
| FR-014 | `subscribe()` drives the generator's submit button |
| FR-015 | Two-failure staleness marker; recovery is the next successful poll |
| FR-017 | Already true — the archive persists reels independently. Verified, not built. |
| FR-018 | `stage` mapped to its existing display name in the bar |
