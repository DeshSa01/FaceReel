# HTTP Contract Changes: 004 UI Overhaul

Only additions and changes are listed. Every endpoint not mentioned keeps its 003
contract exactly. The pages depend on all of them (FR-044 parity).

---

## New routes

### `GET /static/{path}`: shared assets (replaces `GET /static/progress.js`)

- Serves a file **only** if `path` is in the allow-list built at start-up (research D14).
  The allow-list holds every file under `static/css/`, `static/js/` and `static/brand/`,
  plus `static/progress.js`, `static/icons.svg` and `static/manifest.webmanifest`.
- `200`, with the media type from the extension: `.css` → `text/css`, `.js` →
  `application/javascript`, `.svg` → `image/svg+xml`, `.png` → `image/png`,
  `.webmanifest` → `application/manifest+json`.
- Always `Cache-Control: no-cache`.
- `404` for anything not in the allow-list, including the `.html` pages and any path
  containing `..`. The path is never joined to the filesystem before the allow-list lookup.

`/static/progress.js` remains a valid URL, because it is in the allow-list.

### `GET /favicon.ico`

`200 image/png`: the bytes of `static/brand/favicon-32.png`, with `Cache-Control:
no-cache`. Browsers request this path on their own initiative.

### `GET /manifest.webmanifest`

`200 application/manifest+json`: the same file as `/static/manifest.webmanifest`.

Manifest contents (normative fields):

```json
{
  "name": "Supercut",
  "short_name": "Supercut",
  "description": "Every moment they appear, cut into one reel.",
  "start_url": "/",
  "scope": "/",
  "display": "standalone",
  "theme_color": "#5B3DF5",
  "background_color": "#0A0A10",
  "icons": [
    { "src": "/static/brand/icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/static/brand/icon-512.png", "sizes": "512x512", "type": "image/png" },
    { "src": "/static/brand/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable" }
  ]
}
```

### `GET /api/youtube/preview?url=<link>`: title for the link preview (research D7)

| Case | Response |
|---|---|
| No recognisable YouTube video id in `url` | `400 {"detail": "Not a YouTube video link."}` |
| Id recognised; oEmbed succeeded (or was cached) | `200 {"id": "dQw4w9WgXcQ", "title": "…", "author": "…", "thumbnail": "https://i.ytimg.com/vi/dQw4w9WgXcQ/mqdefault.jpg"}` |
| Id recognised; oEmbed failed, timed out (4 s) or the video is private | `200 {"id": "…", "title": null, "author": null, "thumbnail": "https://i.ytimg.com/vi/…/mqdefault.jpg"}` |

Rules:

- The server fetches **only** `https://www.youtube.com/oembed?format=json&url=https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3D<id>`,
  where `<id>` matches `^[A-Za-z0-9_-]{11}$`. The user-supplied URL is never fetched.
- Results, including `title: null` failures, are cached in memory by id, up to 256
  entries, least-recently-used dropped first. A failure is cached for 60 seconds only,
  so a brief YouTube outage doesn't stick.
- Never blocks or affects `POST /api/sessions/{sid}/videos`. The server accepts the same
  links it accepts today.

### `GET /api/archive/{reel_id}`: one archive entry

- `400` for a malformed id (the same `_require_valid_id` as the sibling routes).
- `404` if there is no such entry.
- `200`: exactly the object that entry would have in `GET /api/archive`'s `entries`,
  including `clips` when present.

**Route order**: it must be declared **after** the `/video`, `/thumb` and `/screenshot`
routes. `{reel_id:path}` would otherwise swallow them.

---

## Changed responses

### `GET /api/jobs/active`

- `processing` payloads (`kind: "video"` and `kind: "join"`) gain `elapsed_s` (integer).
  It is absent for the network-wait payload (`stage: "network"`), which is not running.
- `kind: "video"` payloads, including network wait, gain `zoom` (boolean, from the
  video's tuning). The bar's compact stage track needs it to decide whether to show the
  "frame" stage (data-model §7).
- The terminal payload (`kind: "session"`) gains `completed_at` (ISO-8601 string), used
  for the completion key (data-model §3).

### `GET /api/sessions`

Each item gains `video_urls`: an array of up to 4 strings (data-model §4).

### `GET /api/sessions/{sid}`

- Each `processing` video gains `elapsed_s`.
- `join`, while joining, gains `elapsed_s`.

### `GET /api/archive` and the archive sidecar

The response gains `disk_total_bytes` and `disk_free_bytes`, from stdlib
`shutil.disk_usage(ARCHIVE_DIR)`, for the storage meter (FR-039). The archive lives on
the bind-mounted volume, so these are the host drive's real figures. That is what makes
"the drive is filling up" visible, which is the README's stated reason for showing the
total.

Entries may carry `clips` (data-model §1). New session reels have `filename:
"supercut-session-<id>.mp4"`. Existing entries keep their stored `filename`.

---

## Pages

| Page | Change |
|---|---|
| `GET /` | Unchanged route. The page adds a start field (FR-021). |
| `GET /session/{sid}` | Unchanged route. The page accepts an optional `?url=<encoded link>`: it fills the add-video URL field, then removes the parameter with `history.replaceState` (research D8). An unknown session still renders "Session not found". |
| `GET /archive` | Unchanged route. `#<reel id>` still opens that reel's viewer, as today. |

All pages keep `Cache-Control: no-cache`.

---

## Pipeline and archive internals (Python, not HTTP)

These are listed here because the runner, pipeline and archive modules call one another
through them.

| Function | Change |
|---|---|
| `pipeline.cut_and_stitch(...)` | Returns `(output_path, clips)` instead of `output_path`. `clips` comes from probed segment durations (research D13). |
| `pipeline.process_job(...)` | The result dict gains `clips`. |
| `pipeline.join_reels(...)` | The result dict gains `offsets: [float]`, one per input, in input order. |
| `archive.archive_job(...)` | Writes `result["clips"]` to the sidecar when present. |
| `archive.archive_session(sid, path, info)` | Writes `info["clips"]` when present. `filename` becomes `supercut-session-<id>.mp4`. |
| `archive.read_public_entry(reel_id)` | New. One entry in listing shape; `list_entries` uses it per directory, so the two shapes cannot drift. |
| `Runner._run_join` | Builds the session `clips` (data-model §1) from each joined video's sidecar plus `offsets`. |
| `SessionStore.pick_next` | Stamps `started` on the `_runtime` entry. |
| `SessionStore.snapshot` / `active` / `list_open` | Add `elapsed_s`, `zoom`, `completed_at` and `video_urls` as above. |
