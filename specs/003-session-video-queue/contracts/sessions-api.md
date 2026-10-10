# Contract: Sessions API

All routes are served by the single uvicorn worker. **Running more than one worker or replica breaks this contract.** There would be two runners, each believing it is the only consumer, with two writers on `session.json` (constitution, *Single instance, single worker*; research D12).

Ids (`sid`, `vid`) match `^[0-9a-f]{12}$`. A malformed id returns **400 before any filesystem access**. A well-formed but unknown id returns **404**. Error bodies use FastAPI's `{"detail": "<message>"}`.

## Pages

| Route | Serves | Notes |
|---|---|---|
| `GET /` | `static/index.html`, the session chooser | `Cache-Control: no-cache` (unchanged rule) |
| `GET /session/{sid}` | `static/session.html` | Validates `sid` (400). Does **not** 404 an unknown session, because the page renders "Session not found" from the API response. `no-cache` |
| `GET /archive` | unchanged | |
| `GET /static/progress.js` | unchanged route | Content changes (research D9) |

## `GET /api/sessions`

Open sessions (state `open` or `joining`), oldest first.

```json
{
  "sessions": [
    {
      "id": "4f2a91c0be13",
      "created_at": "2026-10-10T14:02:11+01:00",
      "state": "open",
      "title": "First video's title or null",
      "counts": {"waiting": 2, "processing": 1, "done": 1, "failed": 0, "removed": 0},
      "total": 4
    }
  ]
}
```

`total` excludes removed videos. It is the number counted against the 10-video limit.

## `POST /api/sessions`

No body. Returns **201** `{"id": "<sid>"}`. The session starts `open` with no videos.

## `GET /api/sessions/{sid}`

The full session, in any state. Built as a snapshot under the store lock (research D12).

```json
{
  "id": "4f2a91c0be13",
  "created_at": "…",
  "state": "open",
  "completed_at": null,
  "limit": 10,
  "total": 3,
  "will_complete_after_current": true,
  "prefill": {"from_video": "a1b2c3d4e5f6", "tuning": {"lead_in": 0.15, "boundary_reach": 0.6, "clip_gap": 0.6, "zoom": false, "hi_res": false}},
  "videos": [
    {"id": "a1b2c3d4e5f6", "index": 1, "url": "…", "state": "done", "title": "…",
     "tuning": {…}, "result": {"clip_count": 7, "output_duration": 41.2, "resolution": "1920x1080", …}},
    {"id": "…", "index": 2, "state": "processing", "stage": "scan", "progress": 43.5, "message": "…"},
    {"id": "…", "index": 3, "state": "waiting", "line_position": 2}
  ],
  "join": null,
  "result": null,
  "error": null
}
```

- `will_complete_after_current` is true when the session is `open`, one of **this session's** videos is `processing`, and none of this session's videos is `waiting`. Another session's activity never affects it. The page shows the FR-011a warning when it is true.
- `join` is `{"stage": "join", "progress": 0-99, "message": "Normalising reel 2 of 4…"}` while `joining` and running, otherwise `null`.
- `result` follows `data-model.md` once `finished`. `error` is set on `join_failed`.
- `prefill` is `null` until the session has a non-removed video.

## `DELETE /api/sessions/{sid}`

Discards a session that has **never had a video** (FR-024). Returns 200 `{"deleted": "<sid>"}`, or 409 `"Only a session with no videos can be discarded."`. Removes `storage/sessions/<sid>/` and nothing else.

## `POST /api/sessions/{sid}/videos`

`multipart/form-data`, using the same field names as today's `POST /api/jobs` plus one more:

| Field | Required | Notes |
|---|---|---|
| `url` | yes | |
| `screenshot` | one of | Image upload |
| `screenshot_from` | one of | `vid` of a video in this session (research D7) |
| `lead_in`, `boundary_reach`, `clip_gap` | no | Clamped by `Tuning.clamped`, unchanged |
| `zoom`, `hi_res` | no | bool |

Returns **201** `{"id": "<vid>", "index": 3, "line_position": 2}`.

Errors: **409** when the session is at the limit or not `open` (messages in `data-model.md`). **400** when neither or both screenshot fields are given, or `screenshot_from` is not in this session. **404** when the session is unknown.

Effect: the video is persisted, then the runner is notified. If nothing else is in line, processing starts at once (US1 scenario 2).

## `POST /api/sessions/{sid}/retry`

Puts every `failed` video back to `waiting`, in its original order, and reopens an ended session (FR-025). Returns 200 `{"retried": n}`. Returns **409** `"There are no failed videos to retry."`, or `"This session is being joined. Try again when it finishes."`. When the session completes again, its join replaces `storage/archive/<sid>`: the old entry is parked as `.old-<sid>`, the new one is renamed into place, and then the parked one is deleted.

## `DELETE /api/sessions/{sid}/videos/{vid}`

Removes a `waiting` video (FR-012). Returns 200 `{"removed": "<vid>"}`, or **409** `"Only a waiting video can be removed."`. It may complete the session (data-model, spec edge case).

## `GET /api/sessions/{sid}/videos/{vid}/screenshot`

The stored screenshot image, used for the prefill preview. Returns 404 when it is absent.

## `GET /api/sessions/{sid}/output`

The joined reel, `video/mp4`, `Content-Disposition: inline; filename="facereel-session-<sid>.mp4"`. Returns **404** unless the session is `finished` and `storage/archive/<sid>/output.mp4` exists. That second check matters because the user may have deleted the joined reel from the archive. Served from the archive, so it survives a restart (FR-019, SC-004).

## `GET /api/jobs/active` (reshaped)

Still the endpoint `progress.js` polls. The client sends nothing (002 FR-002 preserved).

```json
{"job": {
  "id": "<vid, or sid for a join>",
  "kind": "video",
  "session_id": "4f2a91c0be13",
  "index": 2, "total": 5,
  "status": "processing",
  "stage": "scan", "progress": 43.5, "message": "…"
}}
```

- `index` is the video's `display_index` (data-model), so it always pairs with `total`.
- While a join runs: `kind: "join"`, `id: <sid>`, `stage: "join"`, and `index`/`total` are null.
- With nothing running: the **most recently completed session** (by `completed_at`) as `{"id": sid, "kind": "session", "session_id": sid, "status": "done" | "error", "message": "…"}`. `done` covers `finished` and `nothing_to_join`. `error` covers `join_failed`. Returns `{"job": null}` when no session has ever completed.
- The bar's link for a terminal notice is `/session/<sid>`.

## Removed routes (research D10)

`POST /api/jobs`, `GET /api/jobs/{job_id}`, `GET /api/jobs/{job_id}/output`. Now they hit the 404 / 405 fallthrough. Nothing outside this repository calls them.

## `GET /api/archive` (extended)

Each entry gains `kind` (`"video"` default) and, where present, `session_id` and `videos` (data-model). All other fields and every other archive route are unchanged. `/api/archive/{sid}/video` serves a session reel like any other.
