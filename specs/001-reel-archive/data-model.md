# Phase 1 Data Model: Reel Archive

## On-disk layout

```text
storage/
├── jobs/                        # existing; every subdirectory removed at start-up
│   └── <job_id>/                # working files for an in-flight job
└── archive/                     # new; never touched by the start-up wipe
    ├── .tmp-<reel_id>/          # transient staging; renamed into place, ignored by listing
    └── <reel_id>/               # one complete archived reel
        ├── reel.json            # the sidecar; written last
        ├── output.mp4           # the reel itself
        ├── thumb.jpg            # poster frame; may be absent
        └── screenshot.jpg       # the uploaded reference face image; extension follows the upload
```

Rules that the layout encodes:

- **A directory under `archive/` whose name does not start with `.` is a complete entry.** Guaranteed by assembling in `.tmp-<reel_id>/` and renaming atomically.
- **`reel.json` is written last.** Its presence means the media beside it is fully written.
- **Everything belonging to a reel is inside its own directory.** Deletion is one recursive removal with nothing else to update, satisfying FR-024.
- **`thumb.jpg` is optional.** Its absence is a normal state, not corruption (spec edge case: thumbnail generation may fail).

## Entity: Archived Reel

One finished reel, kept until the user deletes it. Materialised as one directory; identified by `reel_id`.

| Attribute | Source | Notes |
|---|---|---|
| `reel_id` | The job's id | 12 lowercase hex characters, reused from `uuid4().hex[:12]` |
| video | `storage/jobs/<id>/output.mp4`, moved | The only copy after archiving |
| thumbnail | Extracted from the video at archive time | Optional |
| reference image | The uploaded screenshot, moved | Original extension preserved |
| details | `reel.json` | Below |

### Identity and validation

`reel_id` is used to build filesystem paths and appears in URLs, so it is validated **before any path is constructed**:

```text
^[0-9a-f]{12}$
```

Anything else is rejected outright. This is not defence in depth — it is the only thing standing between a URL path segment and `shutil.rmtree`. It lives in `archive.py` so that no endpoint can construct a path without passing through it.

## Entity: Reel Details (`reel.json`)

A single JSON object. Field names mirror what `pipeline.process_job()` already returns and what `Tuning` already holds, so persisting them requires no translation layer.

```json
{
  "id": "4d3d05d8f062",
  "created_at": "2026-09-05T21:14:33+05:30",
  "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "title": "Rick Astley - Never Gonna Give You Up (Official Video) (4K Remaster)",
  "filename": "ricka-20260905-211433.mp4",
  "video": "output.mp4",
  "thumb": "thumb.jpg",
  "screenshot": "screenshot.jpg",
  "clip_count": 12,
  "source_duration": 212.1,
  "output_duration": 48.3,
  "resolution": "1920x1080",
  "zoomed_clips": 3,
  "tuning": {
    "lead_in": 0.15,
    "boundary_reach": 0.6,
    "clip_gap": 0.6,
    "zoom": false,
    "hi_res": false
  }
}
```

| Field | Type | Requirement | Notes |
|---|---|---|---|
| `id` | string | — | Matches the directory name; lets a copied-out entry be identified |
| `created_at` | string | FR-010 | ISO 8601 **with UTC offset**, so a reel's time is unambiguous when `TZ` changes between deployments |
| `url` | string | FR-008 | Source video address |
| `title` | string | FR-006 | May be `""` — `_video_title()` is best-effort and must not fail a job |
| `filename` | string | FR-021 | The download name already produced by `_output_filename()` |
| `video` | string | — | Filename within the entry directory, never a path |
| `thumb` | string \| null | FR-011 | `null` when extraction failed |
| `screenshot` | string \| null | FR-009 | Filename within the entry directory |
| `clip_count` | integer | FR-006 | |
| `source_duration` | number | FR-006 | Seconds |
| `output_duration` | number | FR-006 | Seconds |
| `resolution` | string | FR-006 | `"<width>x<height>"` |
| `zoomed_clips` | integer | FR-006 | `0` when reframing was off |
| `tuning` | object | FR-007 | The five settings, exactly as `Tuning` holds them |

### Why filenames rather than paths

`video`, `thumb` and `screenshot` hold bare filenames relative to the entry directory, never absolute paths. An absolute path baked into a sidecar breaks the moment the archive is moved, restored to a different host, or bind-mounted at a different location — all of which are realistic for this deployment. The reader always joins the filename to the entry directory it just read from.

### Reading rules

- A directory with **no `reel.json`** is skipped — it is either staging debris or an interrupted write.
- A `reel.json` that **fails to parse** causes that entry alone to be skipped; listing continues (FR-018, SC-006).
- A missing **`video`** file marks the entry unavailable rather than removing it, so the user can see something is wrong instead of a reel silently vanishing (spec edge case).
- Unknown fields are ignored, so a future version can add fields without breaking an older reader.

## Entity: Archive

The collection as a whole. Not a stored object — computed on each listing.

| Attribute | Derivation |
|---|---|
| entries | Every valid entry directory, sorted by `created_at` **descending** (FR-014) |
| `total_bytes` | Sum of real file sizes across all entry directories, via `os.scandir` (FR-016) |
| empty state | Zero valid entries (FR-017) |

`total_bytes` is measured, never accumulated from a stored counter, so it cannot drift from what the disk actually holds. Sorting uses recorded `created_at` rather than filesystem mtime, which a copy or restore would rewrite.

## Relationship to existing state

| Existing | Change |
|---|---|
| `jobs` dict in `app.py` | Unchanged in shape. On success, `output_path` is repointed to the archived file so `/api/jobs/{id}/output` keeps working. |
| `clean_jobs_dir()` | **Not modified.** It only ever walks `storage/jobs/`; the archive is out of its reach by construction. |
| `pipeline.process_job()` | **Not modified.** It still returns its result dict; archiving consumes that dict afterwards. |
| Job working directory | Still wiped at start-up. After archiving it holds no reel, only spent working files. |

## Lifecycle

```text
job completes successfully
  └─> create storage/archive/.tmp-<id>/
        ├─ move output.mp4 into it
        ├─ move the reference screenshot into it
        ├─ extract thumb.jpg          (failure here is non-fatal, thumb -> null)
        └─ write reel.json            (last)
      rename .tmp-<id> -> <id>        (atomic; entry becomes visible)
      repoint the job's output_path to the archived video

user deletes an entry
  └─> validate id, then remove storage/archive/<id>/ recursively
      (nothing else references it, so there is no second update)
```
