---

description: "Task list for Persistent Job Progress"
---

# Tasks: Persistent Job Progress

**Input**: Design documents from `/specs/002-persistent-job-progress/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/active-job-api.md, quickstart.md

**Tests**: Not included. The constitution's Development Workflow states the repository has no test suite and this feature does not add one; verification is the manual script in quickstart.md (Polish phase, below).

**Organization**: Tasks are grouped by user story so each can be implemented and demonstrated independently, in priority order.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Every task names an exact file path

## Path Conventions

Single flat project at the repository root: `app.py`, `static/index.html`, `static/archive.html`, `static/progress.js` (new). No `src/`, no build step (plan.md Project Structure).

---

## Phase 1: Setup

Not applicable. Technical Context states no new Python packages, no JavaScript packages, and no build tooling — the two existing hand-written pages plus one new shared script. There is no project scaffolding to initialize.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Server-side changes every user story depends on — the singleton discovery endpoint, the asset route that serves the shared indicator, and the concurrency fix that continuous polling would otherwise turn into a routine crash.

**⚠️ CRITICAL**: All three edit `app.py` and must land before any user story work begins.

- [X] T001 In `app.py`'s `create_job`, seed `"output_path": None` into the job record built at creation (alongside `id`, `status`, `stage`, `progress`, `message`, `result`, `tuning`), so `_worker`'s later `job.update(..., output_path=...)` only ever replaces a value instead of adding a key mid-iteration of `get_job`'s `job.items()`. Add a comment at the seeding line stating that the value is never read and exists only to fix `RuntimeError: dictionary changed size during iteration` under concurrent polling (research D6; data-model.md §1).
- [X] T002 In `app.py`, add `GET /api/jobs/active`, declared immediately above the existing `GET /api/jobs/{job_id}` (T001's route). Selection logic: the record with `status == "processing"` if one exists; otherwise the most recently inserted record in `jobs` (dict insertion order) regardless of state; otherwise return `{"job": null}`. Always returns 200, never 404. Exclude `output_path` from the response exactly as `get_job` already does. Add a comment at the declaration explaining that FastAPI matches routes in declaration order, so declaring this below `/api/jobs/{job_id}` would let `active` be captured as a `job_id` and the endpoint would 404 forever (research D1, D7; contracts/active-job-api.md "Route ordering — load-bearing").
- [X] T003 In `app.py`, add `GET /static/progress.js` returning `FileResponse(os.path.join(BASE_DIR, "static", "progress.js"))` with `Content-Type: application/javascript` and `Cache-Control: no-cache`, following the same pattern as the existing `/` and `/archive` routes. Add a comment noting that without `no-cache`, browsers heuristically cache the script and a stale copy against a redeployed `app.py` would silently stop working (research D3; contracts/active-job-api.md "GET /static/progress.js").

**Checkpoint**: `curl localhost:8765/api/jobs/active` returns `{"job": null}` with a 200 before any job is submitted (quickstart.md step 1); `curl -I localhost:8765/static/progress.js` (once T005 creates the file) returns `no-cache`.

---

## Phase 3: User Story 1 - Reconnect to a reel that is still being made (Priority: P1) 🎯 MVP

**Goal**: A freshly loaded page discovers, on its own and within 2 seconds, whether a reel is being processed and its true current progress — including after the browser was closed entirely and reopened later.

**Independent Test**: Submit a video, close the browser entirely, reopen the application, and confirm the page shows live progress that continues to advance and matches what the server has actually done (quickstart.md steps 1, 2, 4, 5, 8).

### Implementation for User Story 1

- [X] T004 [US1] Verify, with no code change: submit a reel, then quit the browser entirely (not a reload) before it finishes. Confirm via `_worker`'s daemon thread (already in `app.py`, untouched by this feature) that the reel keeps processing and lands in the archive even with no browser open (quickstart.md step 4 pre-check; plan.md "Two things Phase 1 surfaced" — FR-001 and FR-017 are already true and only need confirming here, not building). **Verified 2026-09-06**: submitted a real reel via the API (no browser attached at all — the server cannot distinguish this from a closed browser) and it ran to completion and archived correctly; separately, killed and restarted the server mid-reel and confirmed no half-archived entry.
- [X] T005 [US1] Create `static/progress.js`. On load, inject the indicator's markup and a `<style>` block into `document.head`/`document.body` — a bar fixed to the bottom of the viewport. Style it against the `--card`, `--border`, `--accent`, `--muted`, `--text` custom properties both pages already define, with literal fallback values so it renders correctly on a page that doesn't define them (research D3). Comment the bar's chosen dimensions as arbitrary, not derived (constitution Principle II; plan.md "Note on Principle II").
- [X] T006 [US1] In `static/progress.js`, manage layout so the bar never covers page content: while the bar is shown, measure its rendered height and set `document.body.style.paddingBottom` to that value; clear the padding when the bar is hidden (research D8; FR-016).
- [X] T007 [US1] In `static/progress.js`, implement the poll loop: `fetch("/api/jobs/active")` once per second while `document.visibilityState === "visible"`; stop polling entirely on a `visibilitychange` to hidden; issue one immediate request when the page becomes visible again, rather than waiting for the next tick (research D2; FR-004, FR-013). Comment the 1-second interval as a chosen value — already the existing rate, and half the 2-second requirement (constitution Principle II).
- [X] T008 [US1] In `static/progress.js`, track consecutive failed requests from T007. After 2 in a row, mark the currently displayed figure as not live (a "stale" overlay on whatever state is showing); the next successful response clears that mark automatically, with no reload needed (research D11; FR-015). Comment the two-failure threshold as a chosen value — so a single transient blip is not reported as an outage (constitution Principle II).
- [X] T009 [US1] In `static/progress.js`, add `localStorage` key `facereel.watching`: set it to a job's id whenever that job is rendered as `processing`; clear it when the job reaches a terminal state. When a poll response no longer contains the job named by `facereel.watching` (i.e. `{"job": null}` or a different job), render an "interrupted" state ("did not finish") instead of silently going blank, then clear the key (research D4; data-model.md §3–§4; FR-012).
- [X] T010 [US1] In `static/progress.js`, render the `processing` state from the poll response: map `job.stage` through a display-name table (`start`→"Starting", `reference`→"Reading screenshot", `download`→"Downloading video", `scan`→"Scanning for the person", `refine`→"Refining clip boundaries", `track`→"Measuring framing", `stitch`→"Cutting & stitching", `done`→"Done", mirroring `index.html`'s existing `stageNames`), show `job.progress` as a percentage and `job.message` as status text (FR-018). Render the `absent` state (bar hidden, padding released per T006) when the response is `{"job": null}` or the returned job is terminal (`done`/`error`) — full completed/failed presentation is added in US3 (T016); this pass only needs "not shown as processing."
- [X] T011 [US1] In `static/progress.js`, expose `window.FaceReelProgress.subscribe(callback)`, calling `callback(job)` (the parsed `job` object, or `null`) after every poll resolves, per contracts/active-job-api.md "Page contract for the indicator."
- [X] T012 [US1] In `static/index.html`, add `<script src="/static/progress.js"></script>` before `</body>`, and delete the `poll(id)` function, the `finish()` function, and the `pollTimer` variable (research D10).
- [X] T013 [US1] In `static/index.html`, rewire the submit handler and `#progress-card` to `window.FaceReelProgress.subscribe()` in place of the deleted `poll()` call: show `#progress-card` and update `#stage-label`/`#bar`/`#status-msg` from the subscribed job while `status === "processing"`; disable `#go` and surface the reason in `#form-error` while any job is processing, so the generator makes a second submission's refusal evident before the attempt (FR-014) rather than only after the server's existing 409.

**Checkpoint**: User Story 1 is independently functional — quickstart.md steps 1, 2, 4, 5, and 8 all pass against `static/index.html` alone.

---

## Phase 4: User Story 2 - Watch the archive while a reel is being made (Priority: P2)

**Goal**: The same indicator appears on the archive page, processing is unaffected by navigating there or playing an archived reel, and the indicator never blocks the archive grid.

**Independent Test**: Submit a video, navigate to the archive, play an archived reel end to end, and confirm both that the progress indicator is visible and advancing at the bottom of the archive page and that the new reel completes normally (quickstart.md step 3).

### Implementation for User Story 2

- [X] T014 [US2] In `static/archive.html`, add `<script src="/static/progress.js"></script>` before `</body>`. No markup or CSS of its own is required — the script is drop-in (contracts/active-job-api.md "Page contract for the indicator").
- [ ] T015 [US2] Verify, with no code change expected: with a reel processing, open `/archive` (both by navigating from `/` and by loading it directly in a fresh tab), confirm the bar is present and advancing, scroll to the bottom of the reel grid and confirm the last row is fully visible and clickable (not underneath the bar), play an archived reel through while the new one keeps processing, and navigate back to `/` and confirm the same progress and a disabled submit button (research D8's padding logic from T006 applies unchanged; FR-005, FR-006, FR-016; SC-001, SC-004; quickstart.md step 3). If the bar overlaps the grid or the modal player, fix `static/archive.html`'s layout, not `static/progress.js`.
  **Not yet run**: no browser or browser-automation tool is available in this environment, so the visual overlap/scroll check has not actually been performed. Backing logic was exercised without a real page: the archived-reel-plays-during-processing path was proven live (a real reel completed while archive/API endpoints were hit continuously), and `progress.js`'s padding-reservation code (T006) was verified in a jsdom harness to set/clear `body.style.paddingBottom` correctly. Needs a manual pass in an actual browser before this is truly done.

**Checkpoint**: User Stories 1 and 2 both work independently — quickstart.md step 3 passes in full.

---

## Phase 5: User Story 3 - Learn the outcome wherever you are (Priority: P3)

**Goal**: A finished or failed reel is reported by the indicator on whichever page the user is on, with a way to reach the result, and a dismissed notice stays dismissed.

**Independent Test**: Submit a video, move to the archive, wait for completion, and confirm the indicator reports the finished reel and leads to it (quickstart.md steps 6, 7).

### Implementation for User Story 3

- [X] T016 [US3] In `static/progress.js`, implement the `completed` and `failed` indicator states: when the returned job has `status === "done"` and is not yet acknowledged, show a completion notice linking to `/archive#<job.id>` with a dismiss control (FR-008); when `status === "error"` and not yet acknowledged, show `job.message` as the failure reason with a dismiss control (FR-009, FR-018).
- [X] T017 [US3] In `static/progress.js`, add `localStorage` key `facereel.acknowledged`: set it to the terminal job's id when the user dismisses the notice from T016; suppress the `completed`/`failed` notice for any terminal job whose id matches on this or later polls/reloads (research D5; data-model.md §3; FR-010).
- [X] T018 [US3] In `static/progress.js`, narrow the `absent` condition added in T010 so it fires only when the response is `{"job": null}` or the terminal job has been acknowledged (T017) — a terminal, unacknowledged job now falls through to the `completed`/`failed` rendering from T016 instead (data-model.md §4).
- [X] T019 [US3] In `static/archive.html`, open the matching reel's player both when the page loads with a `#<id>` hash and on `hashchange` while already on the page (not load-only), so the completion notice's `/archive#<id>` link (T016) works from both a fresh navigation and a click while already viewing the archive (research D9; FR-008).
- [ ] T020 [US3] Verify, with no code change expected unless T013's wiring is incomplete: let a reel finish while on `/`, and confirm `#result-card` (stats line, working download link) still appears exactly as it does today, undisturbed by the `subscribe()`-based rewiring from T013 (spec.md Assumptions "The existing generator result view is retained"; User Story 3 Acceptance Scenario 5).
  **Not yet run**: no browser is available in this environment to load `index.html` and watch `#result-card` actually render. The API contract it depends on was verified live (a completed job's `/api/jobs/active` response carries exactly the `result`/`tuning` shape `index.html`'s subscribe callback destructures), and the callback's own control flow (the `watchedId` gate, the done/error branches) was syntax-checked but not executed against a real DOM. Needs a manual pass in an actual browser.

**Checkpoint**: All three user stories are independently functional — quickstart.md steps 1–9 pass in full.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentation truth and the environment-of-record verification the constitution requires before this is done.

- [X] T021 [P] Update `README.md`: correct the statement that progress is watched only on the generator page — it is now visible on every page (constitution Development Workflow "Documentation MUST NOT outlive its truth"; plan.md Project Structure).
- [X] T022 [P] Update `HANDOFF.md` §7: keep the existing "jobs are in-memory: restarting uvicorn loses job history" limitation (still true) and add the user-visible consequence this feature gives it — a restart mid-reel is now reported to the user as an interrupted reel rather than silently vanishing (plan.md Runtime & Deployment Constraints; research D4).
- [~] T023 Run quickstart.md steps 1–10 locally (`.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8765`), including step 10's hammer loop across a reel's completion boundary to confirm T001's fix holds (no `500`s, no `RuntimeError` in the server log).
  **Partially done.** Ran against a real reel (the archived `SA74nvuztRU` source, ~16.5 minutes, 32 clips found), all server-side/API-level: step 1 (`{"job": null}` before submission), step 10 (hammered `/api/jobs/active` and `/api/jobs/{id}` continuously — 2,058 requests spanning the full run and the completion boundary, zero non-200s, no `RuntimeError` in the server log — the T001 fix holds), step 8 (killed and restarted the server mid-reel: `/api/jobs/active` correctly returned `{"job": null}`, no half-archived entry, a new submission was accepted immediately after), and step 4's server-side half (processing continued and archived correctly while driven by nothing but curl — no browser attached at all, which is indistinguishable from a closed one as far as the server is concerned). `progress.js`'s own state machine (processing/stale-recovery/interrupted/completed/acknowledged/failed/absent, plus body-padding reservation) was separately verified via a throwaway jsdom harness (30/31 scripted assertions passed; the one failure was harness timer drift, not a code defect). **Not done**: steps 2, 3, 5, 6, 7, 9 as literally written all require an actual browser (visual bar rendering, multiple windows, `visibilitychange` against a real hidden tab, clicking dismiss/view-reel controls) — no browser or browser-automation tool is available in this environment. A manual pass through quickstart.md in a real browser is still needed to close this out.
- [ ] T024 Build and run the container image per `README.md`, then run quickstart.md steps 2, 3, 4, 6, 11, and 12 against it — specifically step 11 (the `no-cache` header on `/static/progress.js` survives a rebuild) and step 12 (a redeploy mid-reel is reported as interrupted within 5 seconds) — because these are the two checks that only ever fail in the deployed environment, per constitution Principle III.
  **Not run**: Docker is not available in this environment. Everything this step would check has been established at the unit/local level instead — the `no-cache` header was confirmed on the local server's `/static/progress.js` response, and the redeploy-mid-reel behavior is exactly what T023's step-8 local test exercised. Per constitution Principle III ("the container is the source of truth"), this still needs to be run against the actual built image before the feature is considered fully verified.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Not applicable — nothing to do before Foundational.
- **Foundational (Phase 2)**: No dependencies. BLOCKS every user story — `/api/jobs/active` (T002) and `/static/progress.js` (T003) are what US1–US3 all poll and load, and T001 is what keeps continuous polling from crashing the server.
- **User Story 1 (Phase 3)**: Depends only on Foundational. Delivers the MVP on its own.
- **User Story 2 (Phase 4)**: Depends on Foundational and on `static/progress.js` existing (T005–T011 from US1) — it adds one script tag and verifies, rather than writing new indicator logic.
- **User Story 3 (Phase 5)**: Depends on Foundational and on US1's `static/progress.js` (extends the `absent`/`processing` states T010 built with `completed`/`failed`/acknowledgement). Independently testable once present, but not independently buildable before US1.
- **Polish (Phase 6)**: Depends on all three user stories being complete.

### Within Each User Story

- T004–T011 (US1) build one file, `static/progress.js`, layer by layer — markup before layout, layout before polling, polling before stale-handling, all of it before the interrupted/processing/absent rendering and the `subscribe()` hook that exposes it. Each depends on the ones before it in the same file.
- T012–T013 (US1) depend on T011 (`subscribe()` must exist before `index.html` can use it).
- T014 (US2) depends on US1's `static/progress.js` existing. T015 depends on T014.
- T016–T018 (US3) extend `static/progress.js` and depend on T010's `absent`/`processing` states already being in place. T019 depends on T016 (the `/archive#<id>` link it targets). T020 depends on T013.

### Parallel Opportunities

- None within Phase 2 or within any single user story's `static/progress.js` work — every task in T001–T003 and T005–T011/T016–T018 edits the same file as its neighbors.
- T014 (US2, `static/archive.html`) and T019 (US3, `static/archive.html`) are the only story tasks touching a file no other in-flight task touches, but each depends on earlier work in `static/progress.js`, so they follow rather than run alongside it.
- T021 and T022 (Polish) touch different files (`README.md`, `HANDOFF.md`) with no dependency on each other — the one real parallel pair in this task set.

---

## Parallel Example: Polish Phase

```bash
Task: "Update README.md: progress is now visible on every page, not just the generator"
Task: "Update HANDOFF.md §7: in-memory job state now surfaces as a reported interruption, not a silent gap"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 2: Foundational (T001–T003) — the endpoint, the asset route, the concurrency fix.
2. Complete Phase 3: User Story 1 (T004–T013).
3. **STOP and VALIDATE**: run quickstart.md steps 1, 2, 4, 5, 8. A user who closes the browser mid-reel and reopens the app now sees true live progress — the worst gap in the current behaviour is closed.

### Incremental Delivery

1. Foundational → `/api/jobs/active` answerable, `/static/progress.js` servable.
2. Add User Story 1 → validate with quickstart steps 1–2, 4–5, 8 → the generator page alone already delivers SC-002.
3. Add User Story 2 → validate with quickstart step 3 → waiting time becomes usable (the feature's headline ask).
4. Add User Story 3 → validate with quickstart steps 6–7 → nothing finishes unreported.
5. Polish → validate with quickstart steps 9–12, including the container (constitution Principle III).

### Single-Developer Reality Check

This feature has one meaningfully parallel file (`static/progress.js`) built incrementally by a single author, one small backend file (`app.py`) edited three times in sequence, and two small page files (`static/index.html`, `static/archive.html`) each touched twice. There is no multi-developer parallel track here beyond Polish's two documentation files — the task breakdown exists for incremental validation (one user story at a time), not for parallel staffing.
