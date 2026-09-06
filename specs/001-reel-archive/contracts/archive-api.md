# Phase 1 Contract: Archive HTTP API

All paths are relative to the app root. No authentication — the app has none, and runs on a trusted home network (spec Assumptions).

`{id}` is always validated against `^[0-9a-f]{12}$` **before** any filesystem path is built. A malformed id returns `400`, never `404`, so a traversal attempt is distinguishable in the logs from a genuine miss.

## Existing endpoints — unchanged

| Method | Path | Note |
|---|---|---|
| GET | `/` | Landing page. Markup gains an archive link; behaviour unchanged. |
| POST | `/api/jobs` | Unchanged, including the 409 on concurrent submission. |
| GET | `/api/jobs/{job_id}` | Unchanged. |
| GET | `/api/jobs/{job_id}/output` | Unchanged contract. Internally now serves the archived file, because `output_path` is repointed after archiving. |

FR-027 and FR-028 rest on this table staying true.

---

## `GET /archive`

Serves the archive page.

- **200** — `static/archive.html`, with `Cache-Control: no-cache` for the same reason the landing page sets it: `FileResponse` sends no cache headers, so browsers heuristically cache and serve a stale page across restarts.

---

## `GET /api/archive`

Lists every archived reel, newest first, with the archive's total size.

**200**

```json
{
  "total_bytes": 734003200,
  "entries": [
    {
      "id": "4d3d05d8f062",
      "created_at": "2026-09-05T21:14:33+05:30",
      "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
      "title": "Rick Astley - Never Gonna Give You Up (Official Video) (4K Remaster)",
      "filename": "ricka-20260905-211433.mp4",
      "clip_count": 12,
      "source_duration": 212.1,
      "output_duration": 48.3,
      "resolution": "1920x1080",
      "zoomed_clips": 3,
      "size_bytes": 61204480,
      "has_thumb": true,
      "has_screenshot": true,
      "available": true,
      "tuning": {
        "lead_in": 0.15,
        "boundary_reach": 0.6,
        "clip_gap": 0.6,
        "zoom": false,
        "hi_res": false
      }
    }
  ]
}
```

Notes:

- `entries` is **sorted by `created_at` descending** (FR-014). An empty array is the normal empty state (FR-017) — not a 404.
- `size_bytes` is that entry's total on-disk footprint; `total_bytes` is the sum across all entries (FR-016). Both are measured at request time.
- `has_thumb` / `has_screenshot` let the page decide between an image and a placeholder without a failed request per card.
- `available` is `false` when the video file is missing (deleted outside the app). The page shows the entry as unavailable rather than rendering a dead player (spec edge case).
- Entries whose sidecar is missing or unparseable are **omitted**; the rest still list (FR-018, SC-006). A malformed entry never turns this into a 500.
- Absolute filesystem paths are never returned.

---

## `GET /api/archive/{id}/video`

Streams the reel for playback and download.

- **200** — `video/mp4`. Must support HTTP range requests so the player can seek (FR-020).
  - `Content-Disposition: inline`, with the recorded `filename`, matching how `/api/jobs/{id}/output` already behaves so the download name identifies the reel (FR-021).
- **400** — id fails the format check.
- **404** — no such entry, or the entry exists but its video file is gone.

---

## `GET /api/archive/{id}/thumb`

The poster frame for the listing (FR-011).

- **200** — `image/jpeg`.
- **400** — malformed id.
- **404** — no such entry, or no thumbnail was produced. A 404 here is an expected state, since extraction is allowed to fail; the page falls back to a placeholder.

---

## `GET /api/archive/{id}/screenshot`

The reference face image the reel was made from (FR-009).

- **200** — image, content type derived from the stored extension.
- **400** — malformed id.
- **404** — no such entry, or no screenshot stored.

---

## `DELETE /api/archive/{id}`

Permanently deletes one archived reel and everything belonging to it (FR-022, FR-024).

- **200** — `{"deleted": "<id>", "freed_bytes": 61204480}`. `freed_bytes` lets the page update the displayed total without a full re-list.
- **400** — malformed id.
- **404** — no such entry. Deleting an already-deleted entry is a 404, not a silent success, so a double-submit is visible rather than masked.

Semantics:

- Removes the entry directory recursively: video, thumbnail, screenshot and sidecar together.
- **Irreversible.** No soft-delete, no recycle bin — this is what "permanently delete" was taken to mean (spec Assumptions).
- Confirmation is the **client's** responsibility (FR-023). The endpoint does not confirm; it acts. This keeps the destructive step explicit in one place rather than split across a two-call protocol.
- A deleted entry must not reappear, including after restart (FR-025) — guaranteed because the directory was the only record.

---

## Error shape

Errors reuse FastAPI's existing `HTTPException` shape, as the current endpoints already produce:

```json
{"detail": "Archived reel not found."}
```

Messages are written for the user, matching the tone of the existing `"Job not found."` and the pipeline's user-facing failures.
