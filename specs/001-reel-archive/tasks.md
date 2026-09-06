---
description: "Task list for the Reel Archive feature"
---

# Tasks: Reel Archive

**Input**: Design documents from `/specs/001-reel-archive/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/archive-api.md, quickstart.md

**Tests**: No automated test tasks. The repository has no test suite or test dependency, and none was requested; adding pytest is explicitly out of scope per plan.md. Verification is the manual script in `quickstart.md`, referenced from the tasks below.

**Organization**: Grouped by user story so each can be implemented and verified on its own.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable — different file, no dependency on an incomplete task
- **[US1/US2/US3]**: the user story a task serves

## Path Conventions

Flat single-module app at the repository root: `app.py`, `pipeline.py`, `archive.py` (new), `static/`. No `src/` tree.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish the archive location and its constants before anything writes to it.

- [X] T001 Create `archive.py` with the on-disk layout constants — `ARCHIVE_DIR` (`storage/archive`, derived from `os.path.dirname(__file__)` like `JOBS_DIR` in `app.py`), the sidecar filename, and the `.tmp-` staging prefix. Document why the archive sits beside `storage/jobs/` rather than inside it (research D1).
- [X] T002 Add `ensure_archive_dir()` to `archive.py`, creating `ARCHIVE_DIR` with `exist_ok=True`.
- [X] T003 Call `ensure_archive_dir()` from the `lifespan` handler in `app.py`, alongside the existing `clean_jobs_dir()` call. Do **not** modify `clean_jobs_dir()` — the archive is out of its reach by construction (FR-003, FR-005).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The storage primitives every story depends on. Id validation lands here because every later endpoint builds a path from a URL segment.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 Implement `valid_id(reel_id)` in `archive.py` enforcing `^[0-9a-f]{12}$`, and `entry_dir(reel_id)` which validates before joining to `ARCHIVE_DIR` and raises on a bad id. Comment that this is the only barrier between a URL segment and `shutil.rmtree` (research D5).
- [X] T005 Implement `read_entry(reel_id_or_dir)` in `archive.py`: load `reel.json`, return `None` for a missing or unparseable sidecar rather than raising, so one bad entry cannot break a listing (FR-018).
- [X] T006 Implement `_dir_size(path)` in `archive.py` using `os.scandir`, returning total bytes for an entry directory.

**Checkpoint**: `archive.py` can locate, validate and read entries. Story work can begin.

---

## Phase 3: User Story 1 - Reels survive a restart (Priority: P1) 🎯 MVP

**Goal**: A completed reel is written to the archive automatically and is still there, with its details, after a restart.

**Independent Test**: Generate a reel, restart the app, confirm the reel file and its sidecar are both still present and unchanged. Delivers durability with no UI at all.

### Implementation for User Story 1

- [X] T007 [US1] Implement `_make_thumbnail(video_path, dest)` in `archive.py`: one ffmpeg frame grab, seeking a short way in rather than taking frame zero, scaled down to a listing-sized JPEG. Must return a success flag rather than raise — thumbnail failure is non-fatal and leaves `thumb: null` (research D6, spec edge case).
- [X] T008 [US1] Implement `archive_job(...)` in `archive.py` following the lifecycle in data-model.md: create `.tmp-<id>/`, move `output.mp4` in, move the reference screenshot in preserving its extension, attempt the thumbnail, write `reel.json` **last**, then `os.rename` the staging directory into place. Clean up the staging directory on failure and re-raise. Comment that the rename is what makes a half-written entry impossible (research D3).
- [X] T009 [US1] Build the sidecar payload inside `archive_job` exactly per the data-model.md schema: `id`, `created_at` as ISO 8601 **with UTC offset**, `url`, `title`, `filename`, the media filenames, the six stats from `process_job()`'s result, and the five `tuning` values via `dataclasses.asdict`. Store bare filenames, never absolute paths.
- [X] T010 [US1] Call `archive.archive_job(...)` from `_worker` in `app.py` after `process_job` returns, passing the job id, the submitted URL, the result dict, the tuning, and the screenshot path. The URL and screenshot path must be threaded through to `_worker` — check the current signature, which does receive both.
- [X] T011 [US1] Repoint the job's `output_path` to the archived video in the same step, so `GET /api/jobs/{job_id}/output` keeps serving the result card unchanged (FR-027, research D4).
- [X] T012 [US1] Report an archiving failure as a job error with a user-facing message, rather than reporting success for a reel that did not persist (research D8, spec edge case for a full disk).
- [X] T013 [US1] Verify with quickstart.md steps 1 and 2 — including that start-up still logs `Cleared N orphaned job folder(s)` and that `storage/jobs/` is emptied while `storage/archive/` is not.

**Checkpoint**: Reels survive restarts (SC-001). No archive page yet, but the durability problem is solved and verifiable.

---

## Phase 4: User Story 2 - Browse and play past reels (Priority: P2)

**Goal**: An archive page reachable from the landing page lists every reel newest-first as a thumbnail grid, each playable and downloadable.

**Independent Test**: With several reels archived, open the archive page and confirm each lists with its details and image, and each plays to completion and can be seeked.

### Implementation for User Story 2

- [X] T014 [P] [US2] Implement `list_entries()` in `archive.py`: scan `ARCHIVE_DIR`, skip names beginning with `.`, skip entries whose sidecar is missing or unparseable, sort by `created_at` **descending**, and return the entries plus the measured `total_bytes` (FR-014, FR-016, research D7).
- [X] T015 [P] [US2] Per entry, add the derived fields the contract requires: `size_bytes`, `has_thumb`, `has_screenshot`, and `available` (false when the video file is gone, so the page can show it as unavailable instead of a dead player).
- [X] T016 [US2] Add `GET /api/archive` to `app.py` returning the contract's `{total_bytes, entries}` shape. An empty archive returns an empty list with 200, never a 404 (FR-017).
- [X] T017 [P] [US2] Add `GET /api/archive/{id}/video` to `app.py` as a `FileResponse` with `media_type="video/mp4"`, `content_disposition_type="inline"` and the recorded `filename`, mirroring the existing `/api/jobs/{id}/output`. Must answer range requests so the player can seek (FR-020).
- [X] T018 [P] [US2] Add `GET /api/archive/{id}/thumb` and `GET /api/archive/{id}/screenshot` to `app.py`. A missing thumbnail is an expected 404, not an error.
- [X] T019 [US2] Return **400** for an id that fails `valid_id` and **404** for a genuine miss, across every archive endpoint, so a traversal attempt is distinguishable from a normal miss in the logs.
- [X] T020 [US2] Add `GET /archive` to `app.py` serving `static/archive.html` with `Cache-Control: no-cache`, for the same staleness reason the landing page already sets it.
- [X] T021 [US2] Create `static/archive.html`: thumbnail grid, newest first, each card showing the still image (or a placeholder), title, creation date and time, clip count, durations, resolution and the tuning values (FR-015). Include the archive's total size and an explicit empty state.
- [X] T022 [US2] Add the in-page player to `static/archive.html` — selecting a reel plays it with standard controls and offers a download using the recorded filename (FR-019, FR-021).
- [X] T023 [US2] Add a clearly labelled archive link to `static/index.html` (FR-013). Touch only the markup needed for the link; leave the generation form, progress and result logic alone.
- [X] T024 [US2] Verify with quickstart.md steps 3, 4 and 8 — confirm in particular that the ranged request returns **206**, and that the generation flow is unchanged.

**Checkpoint**: Stories 1 and 2 both work. Reels persist and are browsable and playable.

---

## Phase 5: User Story 3 - Delete reels to reclaim space (Priority: P2)

**Goal**: Any archived reel can be permanently deleted after an explicit confirmation, freeing its space.

**Independent Test**: Delete a reel, confirm every file is gone, the entry leaves the list, the total size drops, and it does not return after a restart.

### Implementation for User Story 3

- [X] T025 [US3] Implement `delete_entry(reel_id)` in `archive.py`: validate the id, measure the directory's size first so the freed amount can be reported, then remove it recursively. Return the freed bytes, or `None` when the entry does not exist (FR-024).
- [X] T026 [US3] Add `DELETE /api/archive/{id}` to `app.py` returning `{"deleted": id, "freed_bytes": n}`, **400** on a malformed id, and **404** when the entry is absent so a double-submit is visible rather than masked.
- [X] T027 [US3] Add the delete control and its confirmation step to `static/archive.html`. The confirmation must name the reel being deleted and must state that it cannot be undone (FR-023). Abandoning it leaves the reel untouched.
- [X] T028 [US3] On a successful delete, remove the card and update the displayed total using the returned `freed_bytes`, without a full page reload.
- [X] T029 [US3] Verify with quickstart.md steps 5, 6 and 7 — **run the traversal checks in step 5 before trusting the delete endpoint**, then confirm deletion frees space, is permanent across a restart, and that damaged entries still do not break the listing.

**Checkpoint**: All three stories independently functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T030 [P] Add a README section covering the archive: where it lives, that it is never auto-deleted, that deletion is irreversible, and that the displayed total size is the guard against filling the disk.
- [X] T031 [P] Correct the README's existing statement that `storage/jobs/` being wiped means "download any reel you want to keep before restarting" — that is no longer true and is now actively misleading.
- [X] T032 Note in the README that the archive lives on the bind-mounted volume and therefore survives redeployment, and that a permission error at start-up means the `chown -R 1000:1000` step was skipped.
- [ ] T033 Run the container verification in quickstart.md, including **step 6 — the redeploy test**, which is the scenario that occurs on every new image and is not covered by a restart alone.

---

## Dependencies

```text
Setup (T001-T003)
   └─> Foundational (T004-T006)   ⚠️ blocks everything
          ├─> US1 (T007-T013)  🎯 MVP — durability
          │      └─> US2 (T014-T024)   needs archived entries to list
          │             └─> US3 (T025-T029)   needs a listing to delete from
          └─> Polish (T030-T033)
```

Story order is a genuine data dependency, not a preference: US2 has nothing to display until US1 writes entries, and US3 has nothing to delete until US2 can show it. US1 alone is a shippable improvement — it ends the data loss even with no UI.

## Parallel Execution Examples

**Within Foundational**: T004, T005 and T006 are independent functions in `archive.py` and can be written in any order, though all are in one file.

**Within US2**: T014 and T015 (listing logic in `archive.py`) are independent of T017 and T018 (media endpoints in `app.py`) — different files, no shared state. T021's markup can be drafted against the contract in `contracts/archive-api.md` before the endpoints exist.

**Within Polish**: T030, T031 and T032 all touch `README.md` and must therefore be done together, not in parallel, despite the `[P]` on the first two indicating they are logically independent edits.

## Implementation Strategy

**MVP is User Story 1 alone.** It is the only story that fixes the actual problem — reels being destroyed on restart. Land and verify it before building any UI; if work stops there, the app is materially better and nothing is half-built.

**Then US2**, which makes the durable reels reachable, and **then US3**, which makes the archive maintainable. US3 last is deliberate: a destructive endpoint should not exist before there is a tested listing to confirm it acts on the right entry.

**Two things to get right before anything else ships:**

1. **T004's id validation.** Every archive endpoint builds a filesystem path from a URL segment, and one of them deletes recursively. Land it in the foundational phase and verify it with quickstart step 5.
2. **T008's atomic rename.** Without it, an interrupted archive leaves an entry that lists but will not play — a failure the user only discovers later, when the reel is already unrecoverable.
