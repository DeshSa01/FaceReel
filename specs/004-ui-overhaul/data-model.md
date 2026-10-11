# Data Model: UI/UX Overhaul and Rebrand to Supercut

**Feature**: [spec.md](./spec.md) | **Research**: [research.md](./research.md)

This feature is mostly presentation. The persisted data model changes in exactly one
place: the archive sidecar gains a clip map. Everything else is either in-memory server
state or per-browser preferences.

---

## 1. Clip map (new, persisted in `storage/archive/<id>/reel.json`)

An optional `clips` array, absent on every reel archived before this feature. Readers
MUST treat absence as "no clip information" (FR-043). No migration is needed, and none is
done: existing sidecars are never rewritten (research D17).

### Single-video reel (`kind: "video"`)

```json
"clips": [
  { "start": 0.0,  "end": 4.27,  "source_start": 63.5 },
  { "start": 4.27, "end": 11.9,  "source_start": 142.0 }
]
```

| Field | Type | Meaning |
|---|---|---|
| `start` | number, seconds, 2 dp | Where this clip begins **in the reel**: the running total of the probed segment durations (research D13). |
| `end` | number, seconds, 2 dp | Where it ends in the reel; equals the next clip's `start`. |
| `source_start` | number, seconds, 2 dp | Where the clip was cut from **in the source video**. Recorded because it can't be recovered later. No UI uses it in this feature. |

**Rules**:

- Ordered by `start`, contiguous, and `clips[0].start == 0`.
- `len(clips) == clip_count`.
- The last `end` matches the reel's probed duration to within 0.05 s. A larger mismatch
  means the probe failed, and the writer then omits `clips` rather than writing wrong
  marks.

### Session reel (`kind: "session"`)

```json
"clips": [
  { "start": 0.0,   "end": 4.27,  "video": "a1b2c3d4e5f6", "index": 1, "title": "Interview part 1" },
  { "start": 4.27,  "end": 11.9,  "video": "a1b2c3d4e5f6", "index": 1, "title": "Interview part 1" },
  { "start": 11.9,  "end": 95.4,  "video": "0f9e8d7c6b5a", "index": 2, "title": "Old reel", "whole": true }
]
```

| Field | Type | Meaning |
|---|---|---|
| `start`, `end` | number, seconds, 2 dp | Reel time, i.e. the video's own clip time shifted by its `offset` from `join_reels()`. |
| `video` | 12-hex id | The source video, as in the sidecar's `videos[].vid`. |
| `index` | integer ≥ 1 | The video's display position among the joined videos. |
| `title` | string or null | That video's title, shown when hovering or focusing the strip. |
| `whole` | `true`, optional | The video's own reel had no clip map (it predates this feature), so this one entry spans its whole stretch. |

**Rules**: the same ordering and contiguity rules as above, across all videos. Every
joined video contributes at least one entry. Skipped and failed videos contribute none.

### Where it flows

```text
cut_and_stitch()  ──probe each seg──▶ process_job() result["clips"]
                                          │
archive_job() ────────────────────────────┘──▶ reel.json "clips"   (kind: video)

join_reels() result["offsets"] ─┐
each joined video's reel.json ──┴─▶ Runner._run_join() builds the shifted clips
                                          │
archive_session(info["clips"]) ───────────┘──▶ reel.json "clips"   (kind: session)

reel.json ──▶ archive.list_entries()  (passes sidecar fields through)
          └─▶ GET /api/archive/<id>   (new, one entry)
```

`clips` is **not** copied into `session.json` or the session snapshot's `result`. The
session page fetches it from `GET /api/archive/<id>` once the session has finished. That
keeps `session.json` from duplicating archive data that a deletion would then contradict.

---

## 2. Processing timer (new, in-memory only)

`SessionStore._runtime[<video id or session id>]` gains `started` (a `time.monotonic()`
float), set in `pick_next()` alongside the existing `{stage, progress, message}`.

| Exposed as | Where | Meaning |
|---|---|---|
| `elapsed_s` (integer seconds) | each `processing` video in `GET /api/sessions/<id>`; the `processing` payload of `GET /api/jobs/active`; the session's `join` object while joining | `now - started`, computed server-side (research D11) |

**Lifecycle**: created when a video or join is picked, and discarded with the `_runtime`
entry on done, failed or join result. It does not survive a restart, and that is correct:
the video starts over (003 FR-020).

---

## 3. Terminal-notice identity (changed, API only)

`GET /api/jobs/active`'s terminal payload (`kind: "session"`) gains `completed_at`, the
session's existing field. The browser identifies a completion as:

```text
completion key = "<session id>@<completed_at>"
```

Both the bar's acknowledgement and the celebration use this key (research D12). A retry
clears `completed_at` and the re-join sets a new one, so a rebuilt reel is a new
completion.

---

## 4. Session summary (changed, API only)

`GET /api/sessions` items gain `video_urls`: the URLs of the session's first four
non-removed videos, in order. The home page uses them to draw the session card's
thumbnail strip. Derived on read; not stored.

---

## 5. Per-browser preferences (new, `localStorage`)

Every read and write is wrapped in `try`. When storage is unavailable, each one falls
back to its default and the page works normally (spec edge case).

| Key | Values | Default | Written by | Notes |
|---|---|---|---|---|
| `supercut.theme` | `"light"`, `"dark"`, `"system"` | `"system"` (key absent) | header theme control | Read by the inline head script before first paint (research D2). Other tabs follow through `storage` events. |
| `supercut.archive` | JSON `{ "kind": "all"\|"session"\|"video", "sort": "newest"\|"oldest"\|"longest"\|"largest" }` | `{kind:"all", sort:"newest"}` | archive toolbar | Search text is deliberately **not** persisted (FR-036 says filter and sort). An unknown value falls back to the default. |
| `supercut.notify` | `"accepted"`, `"declined"` | absent = not yet asked | notification offer | `"accepted"` records the user's in-page answer. Browser permission is still checked live, because the user can revoke it in browser settings. |
| `supercut.acknowledged` | completion key | absent | progress bar's Dismiss | Replaces `facereel.acknowledged` (one-time migration, research D12). |
| `supercut.celebrated` | JSON array of completion keys, capped at 50 (oldest dropped) | `[]` | session page after the celebration plays | Bounded so it can't grow forever. 50 is chosen: far more sessions than anyone revisits. |

---

## 6. Brand assets (new, static)

| Asset | Path | Notes |
|---|---|---|
| Mark, full detail | `static/brand/mark.svg` | ≥ 48 px |
| Mark, small optical size | `static/brand/mark-small.svg` | 16–32 px; no cut gap |
| Mark, full-bleed | `static/brand/mark-maskable.svg` | source for the maskable and Apple touch icons: square, opaque, glyph within the central 80% |
| Lockup | `static/brand/logo.svg` | mark plus wordmark |
| Favicon | `static/brand/favicon.svg`, `static/brand/favicon-32.png` | also served at `/favicon.ico` |
| Touch and manifest icons | `static/brand/apple-touch-icon.png` (180), `icon-192.png`, `icon-512.png`, `icon-maskable-512.png` | rendered by `tools/render-icons.sh` (research D6) |
| Manifest | `static/manifest.webmanifest` | also served at `/manifest.webmanifest` |
| Icon sprite | `static/icons.svg` | `<symbol id="i-…">` per icon |
| Empty-state illustrations | `static/brand/empty-sessions.svg`, `empty-archive.svg`, `empty-search.svg` | ≤ 2 KB each, `currentColor` plus gradient |

---

## 7. View state machines (UI)

These are the states the redesign makes visible. None is new server state; each maps
onto states that already exist.

### Video row (session page)

```text
waiting ──picked──▶ processing ──▶ done
   │                  │  ▲
   │                  │  └─(network wait: back to waiting, with countdown; distinct visual, FR-030)
   │                  └──▶ failed ──retry──▶ waiting
   └──remove──▶ removed
```

| State | Badge (icon + label) | Body |
|---|---|---|
| waiting | clock · "#3 in line" | thumbnail, face chip, cross-session wait text, Remove |
| waiting (network) | wifi-off · "Waiting for YouTube" | countdown; stage track in its paused style |
| processing | spinner · "Processing" | stage track, percentage, elapsed time, message |
| done | check · "Done" | clip count, footage length, resolution, "View reel" |
| failed | alert · "Failed" | one-line reason; full detail on hover or focus |
| removed | minus · "Removed" | struck-through title |

### Stage track

The stages shown depend on the video's tuning:

```text
download → scan → refine → [frame] → stitch          ([frame] only when zoom is on)
```

`start` and `reference` are folded into "download" as its preparing phase. They take
under a second, and a stage that flashes past teaches nothing. The pipeline stage names
map onto the track as follows:

| Pipeline stage | Track stage |
|---|---|
| `start`, `reference`, `download` | download |
| `scan` | scan |
| `refine` | refine |
| `track` | frame |
| `stitch` | stitch |
| `network` | the paused style on the current stage |

Joins show a single "Joining reels" stage with its own bar.

### Session page outcomes

```text
open ──queue empties──▶ joining ──▶ finished ──(first view of this completion key)──▶ celebrate once
                                 ├─▶ nothing_to_join
                                 └─▶ join_failed
finished/join_failed ──retry──▶ open   (new completed_at on re-finish ⇒ new completion key)
```
