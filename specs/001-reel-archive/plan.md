# Implementation Plan: Reel Archive

**Branch**: `001-reel-archive` | **Date**: 2026-09-05 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-reel-archive/spec.md`

## Summary

Make finished reels durable and browsable. Today a reel lives in `storage/jobs/<id>/output.mp4` and job records live only in `app.py`'s in-memory `jobs` dict, so `clean_jobs_dir()` destroys every past reel on start-up.

The approach: add a sibling directory `storage/archive/` that the start-up wipe never touches, holding one self-contained directory per reel — the video, a poster frame, the reference face image, and a JSON sidecar of its details. A new `archive.py` module owns that directory; `app.py` gains read/delete endpoints and serves a second static page. `pipeline.py` is untouched.

Two decisions carry most of the design:

- **A JSON sidecar per reel, not one central index.** Deleting is one directory removal, a corrupt entry can only damage itself (FR-018, SC-006), and there is no read-modify-write race on a shared file. Listing reads N small files, which is nothing at personal scale.
- **Entries are assembled in a temp directory and renamed into place.** A directory rename on one filesystem is atomic, so a half-written entry is never visible — which is what the disk-full edge case demands.

## Technical Context

**Language/Version**: Python 3.14 (container and dev venv both), matching the existing app

**Primary Dependencies**: FastAPI + uvicorn (existing), ffmpeg CLI (already in the image, used for the poster frame). No new Python packages.

**Storage**: Plain files on the bind-mounted `storage/` volume. `storage/archive/<id>/` per reel with a `reel.json` sidecar. No database.

**Testing**: The repository currently has no test suite and no test dependency. Verification is the manual end-to-end script in `quickstart.md`. Pure functions in `archive.py` (id validation, sidecar round-trip, size totalling) are written to be unit-testable if a suite is added later, but adding pytest is out of scope here.

**Target Platform**: Linux container (`ghcr.io/deshsa01/facereel`) on an Intel N95 home server, behind Portainer; also runs directly on macOS for development.

**Project Type**: Single small web service — a Python backend serving static HTML pages. No build step, no frontend framework.

**Performance Goals**: Archive listing responds fast enough to feel instant for a few hundred entries. Poster-frame extraction adds well under a second to a job that already takes minutes. Playback supports seeking.

**Constraints**: Single instance, single worker — job state is an in-process dict and the one-at-a-time rule is enforced in-process. Archive writes must survive an abrupt stop without leaving a visible partial entry. Entry ids are used to build filesystem paths and therefore must be validated against traversal.

**Scale/Scope**: Hundreds of reels, one user, trusted home network. No pagination, no accounts, no access control.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Checked against **FaceReel Constitution v1.0.0** (ratified 2026-09-05).

| Principle | Verdict | Evidence in this plan |
|---|---|---|
| I. Explain Why, Not What | **PASS** | Tasks require the atomic-rename reasoning (T008), the sidecar-vs-index reasoning (T001) and the id-validation reasoning (T004) to be comments in the code, not just in these documents. |
| II. Measure Before Tuning | **PASS (narrow)** | The feature introduces no threshold affecting output quality. See the note below. |
| III. Verify In The Environment That Ships | **PASS** | `quickstart.md` splits verification into local and container sections, and step 6 exercises redeployment rather than only a restart. The `available` flag exists because a file's presence is probed rather than assumed. |
| IV. Earn Every Dependency | **PASS** | Zero new Python packages. The poster frame uses the ffmpeg already in the image for the pipeline. |
| V. Destructive Operations Are Explicit And Bounded | **PASS** | `^[0-9a-f]{12}$` validated before any path is built (T004); deletion confined to `ARCHIVE_DIR`; explicit user confirmation (FR-023); no automatic deletion at all (FR-026). |

**Runtime & Deployment Constraints:**

- *Single instance, single worker* — honoured. The per-entry sidecar was chosen partly because it introduces no shared mutable state and needs no lock, so nothing here assumes a single process for correctness even though one is guaranteed.
- *Durable data lives under `storage/`* — the archive is `storage/archive/`, on the bind mount. This is the constraint the feature exists to satisfy.
- *The host is modest* — one frame grab added to a job that already runs for minutes; listing reads a few hundred small files only when the page is opened.
- *Documentation must not outlive its truth* — T031 exists specifically to correct the README's now-false claim that reels must be downloaded before restarting.

**Note on Principle II.** The only arbitrary numbers introduced are the thumbnail's seek offset and its scaled width. Neither affects the reel itself, only a preview image, so no measurement is warranted. Per the principle's intent, these MUST be commented as arbitrary presentation choices rather than dressed up as derived values — the failure mode the principle guards against is a guessed number that later reads as authoritative.

**Post-Phase 1 re-check**: PASS, unchanged. The design adds no service, no dependency, no shared state and no automatic deletion. No Complexity Tracking entry is required.

## Project Structure

### Documentation (this feature)

```text
specs/001-reel-archive/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0 output — decisions and rejected alternatives
├── data-model.md        # Phase 1 output — entities, sidecar schema, on-disk layout
├── quickstart.md        # Phase 1 output — end-to-end verification script
├── contracts/
│   └── archive-api.md   # Phase 1 output — HTTP contract
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2 — created by /speckit-tasks, NOT by this command
```

### Source Code (repository root)

The project is a flat single-module web app; there is no `src/` tree and this feature does not introduce one.

```text
app.py                   # MODIFIED: archive endpoints, /archive page route,
                         #   archive-on-completion in _worker, ensure dir at startup
pipeline.py              # UNCHANGED
archive.py               # NEW: owns storage/archive/ — write, list, read, delete
static/
├── index.html           # MODIFIED: a link to the archive page
└── archive.html         # NEW: grid, player, delete confirmation
storage/
├── jobs/                # UNCHANGED: still wiped at every start-up
└── archive/             # NEW: never wiped
    └── <reel_id>/
        ├── reel.json
        ├── output.mp4
        ├── thumb.jpg
        └── screenshot.jpg
README.md                # MODIFIED: document the archive and its permanence
```

**Structure Decision**: Keep the existing flat layout. A third module, `archive.py`, is added rather than growing `app.py`, because the storage rules (atomic writes, id validation, deletion) are self-contained and are the part most worth testing in isolation. The split mirrors what is already there: `pipeline.py` owns video work, `app.py` owns HTTP, and now `archive.py` owns persistence.

`static/archive.html` is a second standalone page rather than a tab inside `index.html`. The spec asks for a separate page reachable from the landing page, and keeping it separate means the generation flow's markup and script are not touched at all, which is what FR-027 demands. The cost is a small amount of duplicated CSS; extracting a shared stylesheet is deliberately deferred as churn that buys little for two pages.

## Phase 0: Research

See [research.md](./research.md). No `NEEDS CLARIFICATION` markers survived into this plan — the three decisions that would have produced them (retention policy, listing presentation, recorded fields) were settled with the user before the spec was written. Phase 0 therefore documents design decisions and the alternatives rejected, rather than open investigations.

## Phase 1: Design

- [data-model.md](./data-model.md) — the `reel.json` schema, the on-disk layout, and the identity/ordering rules.
- [contracts/archive-api.md](./contracts/archive-api.md) — the five endpoints, their responses, and their error cases.
- [quickstart.md](./quickstart.md) — the end-to-end verification, including the restart test that is the whole point of the feature.

## Implementation Sequence

Ordered so each step is independently verifiable, matching the spec's story priorities.

1. **`archive.py` (P1 core)** — layout constants, id validation, atomic entry write, sidecar read, listing with size totals, deletion. Verifiable in isolation via the Python REPL against a scratch directory.
2. **Archive on completion (P1)** — `app.py`'s `_worker` archives after `process_job` returns; the job's `output_path` is repointed at the archived file so `/api/jobs/{id}/output` keeps working unchanged. Start-up ensures `storage/archive/` exists. **Delivers Story 1: reels survive restart, with no UI yet.**
3. **Read endpoints (P2)** — `GET /api/archive`, `/api/archive/{id}/video`, `/api/archive/{id}/thumb`, `/api/archive/{id}/screenshot`, and the `/archive` page route. Verifiable with curl before any HTML exists.
4. **Archive page (P2)** — `static/archive.html` grid, player, download; link added to `index.html`. **Delivers Story 2.**
5. **Deletion (P2)** — `DELETE /api/archive/{id}` plus the confirmation UI. **Delivers Story 3.**
6. **Docs** — README section covering the archive, its permanence, and that deletion is irreversible.

## Risks

| Risk | Mitigation |
|---|---|
| An id from the URL is used to build a path — traversal or absolute-path injection | Validate against `^[0-9a-f]{12}$` before any path is constructed; reject otherwise. Never join unvalidated input to `ARCHIVE_DIR`. |
| A crash mid-archive leaves a half-written entry that renders broken | Assemble under `storage/archive/.tmp-<id>/`, then rename the directory into place. Listing skips dotted names. |
| Disk fills during archiving | Archive failure is reported against that job; the atomic rename guarantees nothing partial becomes visible. |
| The reel is moved out of the job directory while the result card still points at it | `_worker` repoints `output_path` to the archived file in the same step, so the existing endpoint keeps serving. |
| Archive grows until the disk is full | Accepted deliberately (FR-026). Total size is displayed as the agreed compensating control. |
| Deleting the wrong reel is unrecoverable | Explicit confirmation naming the reel; no other safeguard, matching "permanently delete". |

## Complexity Tracking

No constitution violations to justify — there is no ratified constitution. No entry required.
