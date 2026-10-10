# Implementation Plan: Session Video Queue

**Branch**: `003-session-video-queue` | **Date**: 2026-10-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-session-video-queue/spec.md`

## Summary

Let a user open a server-side **session**, queue up to ten videos in it without waiting for each one, and get one joined reel for the whole session when its queue empties. The reel is identified by the session id.

Today's concurrency model is *one thread per job, refuse with 409 if busy*. This feature inverts it. Submissions are always accepted into a durable line, and **one long-lived runner thread** decides what runs next. Most of the design is about making that line survive the redeploy that every push to `main` triggers.

- **`sessions.py` (new)**: the durable session store. Each session is `storage/sessions/<sid>/session.json` plus its screenshots, rewritten atomically on every state transition. A single lock guards it, and every read hands out snapshots. It owns the session/video state machine, the 10-video limit, auto-completion (FR-011), and restart recovery reconciled against the archive.
- **`runner.py` (new)**: the single consumer. It runs pending joins first, then the first waiting video in queue order (oldest session first, then add order), then parks on a condition variable. It calls the existing `pipeline.process_job` and `archive.archive_job` unchanged.
- **`pipeline.join_reels` (new function)**: concat-copy when every reel's streams match. Otherwise it re-encodes every reel to a common canvas (the most common size and frame rate) with the encoder settings the per-video reels already use.
- **`archive.archive_session` (new function)**: the joined reel becomes an archive entry **keyed by the session id**, with `kind: "session"`. Durability, listing, playback, download, and deletion come from code that already works and already validates ids.
- **Pages**: `/` becomes the session chooser. A new `/session/<sid>` page holds the generator form (moved from `index.html`), the queue, and the joined result. `progress.js` gains session context, and raises one notice per session rather than one per video.
- **Retired**: `POST /api/jobs`, `GET /api/jobs/{id}[/output]`, and the `jobs` dict. Left in place, they would be a second way to start work that bypasses the line.

## Technical Context

**Language/Version**: Python 3.14 (container and dev venv), plus plain browser JavaScript. No bundler or framework, consistent with the existing hand-written pages.

**Primary Dependencies**: FastAPI + uvicorn (existing). ffmpeg/ffprobe (existing system binaries). **No new Python packages, no JavaScript packages, no new system binaries.**

**Storage**: Files under `storage/`. New: `storage/sessions/<sid>/{session.json, screenshots/}`. Archive gains session entries with additive sidecar fields and needs no migration. `storage/jobs/` stays scratch and is still wiped at start-up.

**Testing**: The repository has no test suite and this feature does not add one (constitution, *Development Workflow*). Verification is the manual script in `quickstart.md`. Its decisive steps are a restart mid-queue (local and container), a mixed-resolution join that must decode with zero errors, and join timing measured on the deployment host.

**Target Platform**: Linux container `ghcr.io/deshsa01/facereel` on an Intel N95 home server. Also runs on macOS for development. Browsers: current Chrome, Safari and Firefox.

**Project Type**: Single small web service: a Python backend serving static HTML pages. No build step.

**Performance Goals**: At most 5 s idle between queued videos (SC-002); the runner is woken by a condition variable, not polling. Queue state is reflected within 2 s (FR-015) with 1 s polling on visible pages. A copy-path join takes seconds. The mixed-path join cost is measured, not assumed (quickstart step 14).

**Constraints**: Single instance, single worker, which is now load-bearing twice over: a single runner, and a single writer per `session.json`. Encoding on the host is already the bottleneck. Joins share the same one-at-a-time slot as videos, and the canvas policy is chosen to avoid gratuitous 4K re-encodes. Nothing may require a browser to stay open.

**Scale/Scope**: One user on a trusted network. A handful of open sessions, at most 10 videos each. No accounts or ownership.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Checked against **FaceReel Constitution v1.0.0**.

| Principle | Verdict | Evidence in this plan |
|---|---|---|
| I. Explain Why, Not What | **PASS** | Required comments, by site: why `session.json` is written via `os.replace` (D1); why progress ticks are not persisted (D1); why the runner copies the screenshot rather than letting `archive_job` move it out of the session store (D3); why recovery checks `storage/archive/<vid>` before re-queueing (D3, the crash window); why joins jump the video line (D2); why the join re-encodes *all* reels rather than only the odd ones out (D5, SPS/level mismatch); why the canvas is the mode, not the maximum (D5); why handlers return deep copies (D12); where `MAX_VIDEOS_PER_SESSION = 10` comes from (D11). |
| II. Measure Before Tuning | **PASS, with a recorded obligation** | The one new choice that affects output quality is the join canvas policy (D5). It ships with a required measurement: quickstart step 14, made a task, whose figures go into the code comment. The 10-video limit is a product rule given by the user, not a tuning value. Poll intervals (1 s session page, 2 s chooser) are commented as chosen values. |
| III. Verify In The Environment That Ships | **PASS** | Quickstart separates local from container steps. Step 12 redeploys mid-session, which is the production event FR-020 exists for. Step 13 re-runs the mixed join with the *container's* ffmpeg, since the macOS/Linux ffmpeg divergence is exactly what this principle records. Step 12 also confirms `storage/sessions/` lands on the host bind mount. |
| IV. Earn Every Dependency | **PASS** | Zero new packages. SQLite (stdlib, so free) was still rejected on opacity and the lack of need (D1). |
| V. Destructive Operations Are Explicit And Bounded | **PASS (engaged)** | Two deletions. (1) `DELETE /api/sessions/{sid}` `rmtree`s `storage/sessions/<sid>`: `sid` is validated with `archive.valid_id` before any path is built, it is allowed only for a session that never had a video, and it is user-initiated. (2) Join scratch `storage/jobs/join-<sid>` is removed after each join, inside the existing `clean_jobs_dir` bound. (3) Start-up recovery removes stale `storage/archive/.tmp-<id>` staging folders, only for ids passing `valid_id`. This is automatic, so the README documents it (D3). Removing a *video* deletes nothing (it is a state change), and recovery never deletes an unparseable `session.json` (D3). New ids reaching paths: `sid` and `vid` in every route and in `screenshot_from`, all through the one validator. |

**Runtime & Deployment Constraints:**

- *Single instance, single worker*: **relied upon more heavily than before.** A second worker would mean two runners and two writers per `session.json`, which breaks FR-010 and risks lost updates. The contract states this, and the `docker-compose.yml` comment ("job state lives in a module-level dict") is rewritten to say why.
- *Durable data lives under `storage/`*: sessions go to `storage/sessions/`, a sibling of `jobs/` and `archive/`, never inside `jobs/`.
- *The image is built by CI*: redeploys are routine, which is exactly why the queue is durable (clarification Q4).
- *The host is modest*: one consumer, so sessions add queueing and no parallelism. Joins take the same slot. The canvas policy avoids upscaling a whole session to 4K.
- *Documentation must not outlive its truth*: README (how to use sessions; the auto-completion behaviour; the new automatic directory), HANDOFF (architecture; §7 "jobs are in-memory" limitation now false for sessions), and the `docker-compose.yml` comment are all updated in the same change.

## Project Structure

### Documentation (this feature)

```text
specs/003-session-video-queue/
├── plan.md              # This file
├── research.md          # Phase 0: D1..D12
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   └── sessions-api.md  # Phase 1
├── checklists/
│   └── requirements.md  # from /speckit-specify
└── tasks.md             # Phase 2, created by /speckit-tasks
```

### Source Code (repository root)

```text
app.py                   # lifespan: clean jobs → load+recover sessions → start runner.
                         # + /api/sessions* routes, GET /session/{sid} page route.
                         # GET /api/jobs/active reshaped; POST /api/jobs,
                         # GET /api/jobs/{id}[/output] and the jobs dict removed.
sessions.py              # NEW: SessionStore. Durable store, state machine, limit,
                         # completion, recovery, snapshots, line positions.
runner.py                # NEW: single consumer thread. Joins first, then oldest session's next video.
pipeline.py              # + join_reels(paths, work_dir, progress). process_job unchanged.
archive.py               # + archive_session(); sidecar kind/session_id/videos;
                         # archive_job gains an optional session_id.
static/
├── index.html           # REWRITTEN: session chooser (list + create).
├── session.html         # NEW: generator form (moved from index.html) + queue
│                        # + completion warning + joined-reel player.
├── progress.js          # session-aware labels; per-session terminal notice.
└── archive.html         # session-reel badge and its included-video list.
README.md                # sessions, auto-completion, storage/sessions/
HANDOFF.md               # architecture + limitations updated
docker-compose.yml       # single-instance comment rewritten
```

**Structure Decision**: Keep the flat layout, with `app.py` plus one module per concern. Two concerns are genuinely new and each gets a module: durable session state (`sessions.py`) and execution scheduling (`runner.py`). They are split because the store must be importable and testable by hand without starting a thread, the same reason `clean_jobs_dir` is not at module scope. Media work stays in `pipeline.py` and archive layout in `archive.py`, so the join's ffmpeg and the session entry's sidecar sit next to their existing siblings.

## Post-Design Constitution Re-Check

*Re-evaluated after Phase 1. Verdicts unchanged; the design surfaced three things worth recording.*

| Principle | Verdict | What Phase 1 changed |
|---|---|---|
| I | **PASS** | The required comments are pinned to named functions in `research.md`, so `/speckit-tasks` can make each one part of a task. |
| II | **PASS, with obligation** | The canvas measurement is quickstart step 14 and must become a task. Shipping without it would leave a quality-affecting policy justified only by reasoning. |
| III | **PASS** | Strengthened by step 13: the mixed join's correctness depends on the ffmpeg build, which is precisely what has diverged before. |
| IV | **PASS** | Unchanged. |
| V | **PASS (engaged)** | Design confirmed exactly one new `rmtree` (empty-session discard), bounded and validated. Recovery is non-destructive. |

**Three things Phase 1 surfaced:**

1. **`archive_job` moves the screenshot, which would break restart safety.** If the runner passed the session's screenshot path straight through, `archive_job` would move it out of `storage/sessions/`. A crash after that would leave a waiting video with no screenshot to process, and a later video could no longer be prefilled from it. The fix is in the runner (copy into the job dir first), not in `archive.py`, so the archive feature's contract stays untouched (D3).
2. **There are two crash windows that recovery must handle.** The first sits between `archive_job`'s rename and the next `session.json` write. A naive "processing → waiting" reset would re-run the video and then fail on the existing archive directory, so recovery uses the archive as the tiebreaker (D3), and quickstart step 6 forces that window deliberately. The second is inside the archive step itself: a stale `archive/.tmp-<id>` would make the retry fail with `FileExistsError`. Recovery removes such staging folders first (D3).
3. **002's "never goes backwards" progress (002 FR-007) is knowingly relaxed across a restart.** A resumed video starts from 0%. That is the truthful picture under this spec's FR-020, which replaces 002's "report it as interrupted" with "carry on". Recorded here so it is not mistaken for a regression.

## Complexity Tracking

> No Constitution Check violations. This section is intentionally empty.
