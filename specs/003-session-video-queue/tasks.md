---

description: "Task list for Session Video Queue"
---

# Tasks: Session Video Queue

**Input**: Design documents from `/specs/003-session-video-queue/`

**Prerequisites**: plan.md, spec.md, research.md (D1–D12), data-model.md, contracts/sessions-api.md, quickstart.md

**Tests**: Not included. The constitution's Development Workflow states the repository has no test suite and this feature does not add one. Verification is the manual script in quickstart.md. Each story phase ends with the quickstart steps that prove it, and the Polish phase covers the container steps.

**Organization**: Tasks are grouped by user story so each can be implemented and demonstrated in priority order.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: Which user story this task belongs to (US1–US4)
- Every task names an exact file path

## Path Conventions

This is a single flat project at the repository root: `app.py`, `sessions.py` (new), `runner.py` (new), `pipeline.py`, `archive.py`, `static/*.html`, `static/progress.js`. There is no `src/` and no build step (plan.md Project Structure). Run locally with `.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8765`.

---

## Phase 1: Setup

Not applicable. Technical Context lists no new Python packages, JavaScript packages, or system binaries, so there is nothing to install or scaffold.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The durable store, the single runner, and the removal of the old per-job model. Every story builds on these.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T001 Create `sessions.py` with the module docstring explaining why `storage/sessions/` is a sibling of `storage/jobs/` and `storage/archive/`, not inside `jobs/` (research D1). Add constants `SESSIONS_DIR = storage/sessions`, `SESSION_FILE = "session.json"`, and `MAX_VIDEOS_PER_SESSION = 10`, the last commented as a product rule from the user, not a tuning value (research D11). Add `ensure_sessions_dir()`. Add `session_dir(sid)`, which calls `archive.valid_id` and raises `ValueError` before joining any path (Constitution V, FR-023), plus `screenshots_dir(sid)`. Add `_now()`, returning ISO-8601 with UTC offset in the same format as `archive.archive_job`'s `created_at`.
- [X] T002 In `sessions.py`, add `_write_session(record)`: write `session.json.tmp`, then `os.replace` it onto `session.json`. Comment why: atomic on one filesystem, so a crash leaves the old or the new file, never a torn one (research D1). Add `_read_session(path)`, which returns `None` and logs on an unparseable file and never deletes it (research D3).
- [X] T003 In `sessions.py`, implement `class SessionStore`. It holds `self._lock = threading.Lock()` and `self.changed = threading.Condition(self._lock)`; `self._sessions: dict[sid, record]`; `self._runtime: dict[vid_or_sid, {stage, progress, message}]`, commented that progress ticks are memory-only, so there is no disk I/O per tick on an encode-bound host (research D1); and `self._next_seq`. Add `load()`, which reads every `SESSIONS_DIR/*/session.json`, skips bad files, and sets `_next_seq = max(seq) + 1`. Add `_new_id()`, which uses `uuid4().hex[:12]` and re-rolls on a collision with any session dir, any video id, or `archive.ARCHIVE_DIR/<id>` (data-model Identifiers, research D6). Add `create_session()`, which writes `{id, created_at, state:"open", videos:[], completed_at:None, result:None, error:None}` and returns the sid.
- [X] T004 In `sessions.py`, add `snapshot(sid)` and `list_open()`. Both return `copy.deepcopy` data built under the lock, merging each video's `_runtime` progress, never live references. Comment the 002 research D6 `RuntimeError` this prevents (research D12). Add derived fields: `counts`, `total` (excluding `removed`), `title` (the first video's title), `limit`, and `prefill` (data-model Session "Derived"). Add `line_position` for waiting videos: 1 + the number of waiting videos with a lower `seq` in any session + 1 if anything is processing or joining (data-model Video "Derived"). Add `display_index` per data-model, and use it (not `index`) in `active()` and every user-facing "video N of M".
- [X] T005 [P] In `archive.py`, give `archive_job` an optional `session_id=None` parameter and write `"kind": "video"` plus `"session_id"` (when given) into the sidecar. In `list_entries`, default a missing `kind` to `"video"` so existing archives need no migration (data-model "Archive sidecar extension").
- [X] T006 Create `runner.py` with `class Runner(store)` and `start()`, which spawns one daemon thread. In the docstring, explain why one consumer replaces one-thread-per-job: FR-010 holds by construction (research D2). Its loop, under `store.changed`: `pick_next()` returns the waiting video with the lowest `seq` across all sessions, or `None`, in which case it calls `store.changed.wait()`. In `sessions.py`, add `SessionStore.mark_processing(sid, vid)`, `set_progress(key, stage, pct, message)`, `mark_done(sid, vid, result, title)`, and `mark_failed(sid, vid, error)`. Each of the state-changing ones persists via `_write_session`.
- [X] T007 In `runner.py`, implement `_run_video(sid, video)`, which runs outside the lock. Create `storage/jobs/<vid>/` and **copy** (`shutil.copy2`) the session's screenshot into it. Comment that `archive_job` *moves* its screenshot, and passing the session copy would strip it from the store and break restart and prefill (research D3, plan "Three things" #1). Build `pipeline.Tuning(**video["tuning"])` and call `pipeline.process_job` with a progress callback mirroring today's `_worker` (`min(pct, 99)`, rounded). On success call `archive.archive_job(vid, url, result, tuning, job_screenshot, session_id=sid)` and then `store.mark_done`. On `PipelineError` or any exception, or on an archive failure, call `store.mark_failed` with today's messages, including "Reel was generated but could not be saved: …" (FR-014: then continue to the next video).
- [X] T008 In `app.py`, delete the module-level `jobs`/`jobs_lock`, `_worker`, `POST /api/jobs`, `GET /api/jobs/{job_id}`, `GET /api/jobs/{job_id}/output`, and the route-order comment above `/api/jobs/active`, which no longer applies once `{job_id}` is gone (research D10). Create `store = sessions.SessionStore()` and `runner = runner.Runner(store)` at module scope **without side effects**. In `lifespan`, in order: `clean_jobs_dir()` → `archive.ensure_archive_dir()` → `sessions.ensure_sessions_dir()` → `store.load()` → `store.recover()` → `runner.start()`. Comment that the order matters: recovery must see the archive before the runner can pick work. Stub `store.recover()` as a no-op until T015.
- [X] T009 In `app.py`, reshape `GET /api/jobs/active` per contracts/sessions-api.md. While a video is processing, return `{id: vid, kind:"video", session_id, index, total, status:"processing", stage, progress, message}`; otherwise return `{"job": null}`. The join and terminal-session shapes arrive in US2 (T023). Add `SessionStore.active()` in `sessions.py` to build this under the lock.

**Checkpoint**: The app starts, `curl /api/jobs/active` returns `{"job": null}`, and `storage/sessions/` exists. No UI can queue anything yet.

---

## Phase 3: User Story 1 — Queue several videos in one session (Priority: P1) 🎯 MVP

**Goal**: Create a session and add videos while one is processing. They run one at a time in the order added and survive the browser closing and an application restart. Each produces its own archived reel.

**Independent Test**: Create a session, add three videos in quick succession, close the browser, and return later. All three ran in order and each is in the archive (quickstart steps 1–3 and 6).

- [X] T010 [US1] In `sessions.py`, add `SessionStore.add_video(sid, url, tuning, screenshot_upload=None, screenshot_from=None)`. Under the lock: 404 when the session is unknown (raise a `SessionError` subclass carrying the status); 409 when the session is not `open`, or has `MAX_VIDEOS_PER_SESSION` non-removed videos, with the messages from data-model "Limits and validation"; 400 when neither or both screenshot sources are given, or `screenshot_from` is not a video in **this** session (validate it with `archive.valid_id` first). Save the screenshot as `screenshots/<vid><ext>`. For `screenshot_from`, copy the referenced file. Append `{id, seq, index, url, screenshot, tuning, state:"waiting", added_at, finished_at:None, title:None, result:None, error:None}`, persist, then `self.changed.notify()`. Return `{id, index, line_position}`.
- [X] T011 [US1] In `app.py`, add `POST /api/sessions` (201, `{"id": sid}`), `GET /api/sessions/{sid}` (snapshot, or 404), `POST /api/sessions/{sid}/videos` (multipart fields as in the contract; tuning via `pipeline.Tuning.clamped` and stored as `asdict`; 201), and `GET /api/sessions/{sid}/videos/{vid}/screenshot`. Map `SessionError` to `HTTPException`. Every route validates `sid` and `vid` with the existing `_require_valid_id` pattern (400 before any path use). Generalise its message from "reel id" to "id", or add a sibling helper.
- [X] T012 [US1] In `app.py`, add the page route `GET /session/{sid}`. Return 400 for a malformed `sid`; otherwise serve `static/session.html` with `Cache-Control: no-cache`, the same as `index()`. Do not 404 unknown sessions, because the page renders "Session not found" from the API (contract "Pages").
- [X] T013 [US1] Create `static/session.html` by **moving** the generator from `static/index.html`: the `<style>` block, the form (URL, screenshot drop, zoom, 4K, outcome line, fine-tuning sliders, recommended, reset), and their scripts. Change the submit handler to `POST /api/sessions/{sid}/videos` (sid from `location.pathname`) and show 409/400 `detail` in `#form-error`. After a successful add, clear only the URL field (FR-007). Include `<script src="/static/progress.js">` and a link back to `/` and `/archive`. Do **not** move the `window.FaceReelProgress.subscribe(...)` handler, `watchedId`, or the `#progress-card`/`#result-card` logic. The handler disables submit whenever anything is processing, which contradicts FR-006, and the result card reads the removed `/api/jobs/{id}/output`. T014's queue poll replaces all of it.
- [X] T014 [US1] In `static/session.html`, add the queue card. Poll `GET /api/sessions/{sid}` every 1 s while `!document.hidden` and immediately on `visibilitychange`; comment this as the existing rate, half the 2 s FR-015 bound (Principle II, research D9). Render each video with index, title or URL, and state: waiting with "#N in line", processing with stage name, bar and message (reusing `stageNames`), done with clip count and footage seconds and a link to `/archive#<vid>`, failed with the reason in `--error` colour. Show "x of 10" and disable the form at the limit. Implement **prefill** (research D7): when `prefill` is non-null and the user has not picked a file, show the preview from `/api/sessions/{sid}/videos/{from_video}/screenshot`, set the sliders and checkboxes from `prefill.tuning` once per new `from_video` (do not fight user edits), submit `screenshot_from`, and offer "Use a different screenshot", which reverts to the file picker. Show "Session not found" on 404. Show the full session id in the page header, with a copy button (FR-002).
- [X] T015 [US1] In `sessions.py`, implement `SessionStore.recover()` (research D3). For each video in `processing`: if `os.path.isdir(archive.entry_dir(vid))`, mark it `done` (read title and result from the archive sidecar via `archive.read_entry`); otherwise reset it to `waiting`, keeping its `seq`. Never mark a video `failed` because of a restart (FR-020). Comment the single crash window between `archive_job`'s rename and the session write, and why a naive reset would fail on the existing archive dir. Persist every changed session and log one summary line, as `clean_jobs_dir` does. **First**, before touching any session, `shutil.rmtree` every `archive.ARCHIVE_DIR/.tmp-<id>` whose `<id>` passes `archive.valid_id`, and log the count. Comment the second crash window (research D3).
- [X] T016 [US1] Rewrite `static/index.html` as the minimal **chooser**: title, the "View archived reels" link, and a **Create session** button that `POST /api/sessions` and navigates to `/session/<id>` (FR-001; US1 scenario 1). Keep the `:root` colour tokens and dark mode. Include `progress.js`. The running-session list arrives in US3 (T030).
- [X] T017 [US1] In `static/progress.js`, make the processing render session-aware. The stage line becomes `Session <first 6 chars of session_id>… · video <index> of <total> · <stage name>` (FR-016), and the bar links to `/session/<session_id>`. **Delete** the "watched id vanished" branch (`WATCH_KEY`, `getWatching`/`setWatching`, `renderInterrupted`). With a queue, `active` changes id at every normal hand-off between videos, so that check would fire after every successful video. Restarts now re-queue rather than lose work (FR-020), so there is nothing left for it to detect. Add a comment saying why it was removed, and that a resumed video legitimately restarts at 0% (research D9, plan "Three things" #3).
- [X] T018 [US1] Run quickstart steps 1, 2, 3 and 6, including the crash-window variant, locally, and fix whatever fails.

**Checkpoint**: The MVP is complete. Videos queue, run in order, survive closing the browser and a restart, and each lands in the archive. Sessions stay `open` indefinitely, because completion and joining are US2.

---

## Phase 4: User Story 2 — One joined reel for the whole session (Priority: P2)

**Goal**: When a session's queue empties, it completes, stops accepting videos, and joins its videos' reels in order into one reel. That reel is identified by the session id, plays straight through across resolutions, and persists in the archive.

**Independent Test**: A two-video session ends with one reel whose length equals the sum of both, retrievable at `/api/sessions/<sid>/output` (quickstart steps 4, 8 and 9).

- [X] T019 [US2] In `sessions.py`, add `_maybe_complete(session)`, called under the lock from `mark_done`, `mark_failed` and (in US4) `remove_video`. If the session is `open`, has ≥1 video, and none is `waiting` or `processing`, set `state="joining"` and `completed_at`, persist, and `notify()` (research D4). In `snapshot`, add `will_complete_after_current` and `join` (runtime progress for `sid`) per the contract. Confirm `add_video`'s `open` check is under the same lock as completion, and comment the add-vs-complete race it settles.
- [X] T020 [P] [US2] In `pipeline.py`, add `_probe_reel(path)`, which uses ffprobe to read width, height, sample_aspect_ratio, avg_frame_rate, pix_fmt, has_audio, sample_rate and channels. Add `join_reels(paths, work_dir, progress)` (research D5). If every probe matches, concat-demux with `-c copy -movflags +faststart` using absolute paths (cite the existing concat comment). Otherwise pick the canvas as the most common `(w, h, fps)`, ties going to the larger area, and re-encode **every** reel into `work_dir/norm_NNNN.mp4` with `scale=W:H:force_original_aspect_ratio=decrease,pad=W:H:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=F`, the same `libx264 -preset medium -crf 18`, `aac -ac 2 -ar 44100` and `-video_track_timescale 90000` as `cut_and_stitch`, adding `anullsrc` silence for a reel with no audio. Then concat-copy. Report progress per reel ("Normalising reel i of n…") under stage `"join"`. Return the output path, duration and resolution. Comment (a) why everything is re-encoded rather than only the odd ones out (SPS/level mismatch under stream copy) and (b) why the canvas is the mode, not the max, with a placeholder `MEASURED: <fill from T037>` (Principle II).
- [X] T021 [P] [US2] In `archive.py`, add `archive_session(sid, joined_path, summary)`, mirroring `archive_job`'s staging-then-`os.rename` pattern and its failure cleanup. Write a sidecar with `kind:"session"`, `title:"Session <sid> · N videos"`, `filename:"facereel-session-<sid>.mp4"`, `url:null`, `screenshot:null`, summed `clip_count`, `output_duration`, `resolution`, and `videos:[{vid,title,url,state,reason?}]` in session order. Generate a thumbnail with `_make_thumbnail`. Make `list_entries` pass through `kind`, `session_id` and `videos`.
- [X] T022 [US2] In `runner.py`, give joins priority: before picking a video, take the `joining` session with the oldest `completed_at`, and comment why joins jump the line (research D2). In `_run_join(sid)`, collect `storage/archive/<vid>/output.mp4` for `done` videos in order, skipping any the user has deleted from the archive and recording them as skipped (research D6). With no inputs, call `store.mark_join_result(sid, "nothing_to_join")`. Otherwise run `pipeline.join_reels` in `storage/jobs/join-<sid>/`, then `archive.archive_session`, then mark `finished` with `result`. On any exception, mark `join_failed` with `error`; individual reels are untouched (FR-022). Add `mark_join_result` to `sessions.py`. After the join, whether it succeeded or failed, `shutil.rmtree` `storage/jobs/join-<sid>/`. It is inside the existing `clean_jobs_dir` bound, and `sid` is already validated. Otherwise up to 10 re-encoded reels sit on disk until the next restart.
- [X] T023 [US2] In `sessions.py` `recover()`, add: a `joining` session becomes `finished` if `archive.entry_dir(sid)` exists, and otherwise stays `joining` for retry. An `open` session with ≥1 video, all terminal, goes through `_maybe_complete` (research D3). In `SessionStore.active()`, return the join shape (`kind:"join"`, `id:sid`, `stage:"join"`) while a join runs. When idle, return the most recently completed session as `kind:"session"` with `status "done"` (finished or nothing_to_join) or `"error"` (join_failed) and a message (contract `/api/jobs/active`).
- [X] T024 [US2] In `app.py`, add `GET /api/sessions/{sid}/output`. Validate the id, then return 404 unless the session is `finished` and `archive/<sid>/output.mp4` exists. Serve a `FileResponse` with `video/mp4`, `filename=facereel-session-<sid>.mp4` and `inline` (FR-019, contract).
- [X] T025 [US2] In `static/session.html`, when `will_complete_after_current` is true, show the FR-011a warning above the form: "This session will finish and be joined when the current video completes — add another video now to keep it open." While `joining`, show a join progress bar and disable the form. On `finished`, show the result card (player `src=/api/sessions/{sid}/output`, download link, stats: joined count, duration, resolution, and any skipped or failed videos with reasons) and a **Start a new session** button. On `nothing_to_join` or `join_failed`, show the reason and the same button. On a 409 "session has completed" from an add, offer the same button (spec edge case).
- [X] T026 [US2] In `static/progress.js`, handle the new `active` shapes. For `kind:"join"`, use the stage line "Session <sid…> · joining reels". For a terminal `kind:"session"`, show "Session reel ready" (done with a result), "Session finished — nothing to join", or "Session reel failed" (error), with the link `/session/<sid>` instead of `/archive#<id>`. Keep the existing acknowledgement mechanism, now keyed by session id, so per-video completions no longer raise a notice (research D9).
- [X] T027 [P] [US2] In `static/archive.html`, mark `kind === "session"` entries with a "Session" badge. In the opened entry's detail, list its `videos` (title or URL, state, and reason when skipped or failed). Hide the screenshot control for session entries (`has_screenshot` is false). For video entries with `session_id`, show a small "from session <sid…>" link to `/session/<sid>`.
- [X] T028 [US2] Run quickstart steps 4, 8 and 9 locally. Step 8 must print `CLEAN` from `ffmpeg -v error … -f null -` and play through the transition in Safari and Chrome. Fix whatever fails.

**Checkpoint**: Sessions complete on their own and produce one durable joined reel, found by session id.

---

## Phase 5: User Story 3 — Join a running session from any browser (Priority: P3)

**Goal**: Opening `/` on any device lists running sessions, with enough detail to recognise them, and lets the user join one.

**Independent Test**: Create a session in browser A and add a video. In browser B, the session is listed; join it, add a video, and both browsers show the same queue (quickstart step 7).

- [X] T029 [US3] In `app.py`, add `GET /api/sessions` returning `{"sessions": store.list_open()}`: states `open` and `joining`, oldest first, with `id`, `created_at`, `state`, `title`, `counts` and `total` (contract, FR-003).
- [X] T030 [US3] In `static/index.html`, add the running-sessions list above **Create session**. Each row shows the short id, created time (locale-formatted), first video title (or "No videos yet"), and counts (e.g. "1 processing · 2 waiting · 1 done"), with a **Join** link to `/session/<id>`. With an empty list, show only Create (FR-001). Poll every 2 s while visible, commented as a chosen value since the chooser is not a progress view (Principle II).
- [X] T031 [US3] Run quickstart step 7 with two different browsers and fix whatever fails.

**Checkpoint**: Sessions are discoverable and joinable from any device.

---

## Phase 6: User Story 4 — Manage what is waiting (Priority: P4)

**Goal**: Remove a waiting video before it runs, and discard a session that never had a video.

**Independent Test**: Queue three videos and remove the third while it waits. It never runs and is absent from the joined reel. An empty session can be discarded (quickstart steps 5 and 10).

- [X] T032 [US4] In `sessions.py`, add `remove_video(sid, vid)`, which under the lock returns 409 unless the video is `waiting`, sets `removed`, persists, and calls `_maybe_complete` (spec edge case: removing the last waiting video can complete the session). Add `discard_session(sid)`, which returns 409 unless the session has **never** had a video (`videos == []`) and otherwise `shutil.rmtree(session_dir(sid))` after `valid_id`. Comment the Principle V bound: validated id, confined to `storage/sessions/<sid>`, user-initiated only (FR-024, research D11).
- [X] T033 [US4] In `app.py`, add `DELETE /api/sessions/{sid}/videos/{vid}` (200 `{"removed": vid}`) and `DELETE /api/sessions/{sid}` (200 `{"deleted": sid}`), with the 400/404/409 mapping from the contract.
- [X] T034 [P] [US4] In `static/session.html`, add a **Remove** control on waiting rows only, with no confirm() dialog (consistent with the archive page). Show removed rows struck through. When the session has no videos, add a **Discard session** control that navigates to `/` on success.
- [X] T035 [US4] Run quickstart steps 5, 10 and 11 and fix whatever fails.

**Checkpoint**: All four stories work locally.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T036 Audit the required "why" comments listed in plan.md's Constitution Check, Principle I row, against the code. Each named site must carry its comment: `_write_session`, `_runtime`, `_run_video` copy, `recover`, the joins-first ordering, `join_reels` (re-encode-all and canvas), `snapshot` deep copies, and `MAX_VIDEOS_PER_SESSION`. Run `.venv/bin/python -m py_compile app.py sessions.py runner.py pipeline.py archive.py`.
- [ ] T037 On the nucbox, measure join wall-clock for quickstart step 14 (a) copy-path, (b) mixed under mode-canvas, and (c) mixed under max-canvas, toggled temporarily. Replace the `MEASURED:` placeholder in the canvas comment in `pipeline.py` with the figures. Revisit the policy if they contradict research D5 (Principle II).
- [X] T038 [P] Update `README.md`. Cover: the session chooser and session page; that a session completes and joins **automatically when its queue empties**, so add videos while earlier ones run; the 10-video limit; where joined reels appear (archive, "Session" badge, `/api/sessions/<sid>/output`); that sessions resume after a restart with the interrupted video starting over; and the new `storage/sessions/` directory and its one deletion path (empty-session discard). Constitution V requires automatic deletion to be documented, and this deletion is manual, but list it anyway. Also document the one new **automatic** deletion: start-up removes half-written archive staging folders (`storage/archive/.tmp-*`) left by a crash (research D3).
- [X] T039 [P] Update `HANDOFF.md`. Rewrite the architecture to cover `sessions.py`, `runner.py`, `join_reels` and `archive_session`. Restate the §7 "jobs are in-memory" limitation, since sessions are now durable while per-tick progress is not. Record the retired `/api/jobs` routes and this feature in the features list.
- [X] T040 [P] Rewrite the closing comment in `docker-compose.yml`. Single instance still holds, now because there is one runner thread and one writer per `session.json`, not because of a module-level dict and a 409.
- [ ] T041 Merge `003-session-video-queue` to `main`, let CI publish the image, deploy, and run quickstart steps 12 (redeploy mid-session; confirm `session.json` on the host bind mount) and 13 (mixed join decodes `CLEAN` with the container's ffmpeg via `docker exec`). Record any macOS/Linux divergence in `HANDOFF.md` (Principle III).

---

## Dependencies & Execution Order

### Phase dependencies

- **Foundational (T001–T009)** blocks everything. T001→T002→T003→T004 are sequential in `sessions.py`. T005 (`archive.py`) can run alongside T001–T004. T006–T007 need T003 and T005. T008–T009 need T006.
- **US1 (T010–T018)** needs Foundational. It is the MVP.
- **US2 (T019–T028)** needs US1, since the joins consume US1's per-video reels and the session page from T013/T014. T020 (`pipeline.py`) and T021 (`archive.py`) are independent of each other and of T019, so they can start as soon as Foundational is done.
- **US3 (T029–T031)** needs only US1's T011 and T016. It can be built in parallel with US2.
- **US4 (T032–T035)** needs US1. Its "removal completes the session" behaviour needs US2's `_maybe_complete` (T019). Built before US2, removal still works, but the session will not complete until T019 lands.
- **Polish (T036–T041)** needs every story it documents. T037 and T041 need a deployed build.

### Within each story

`sessions.py` (state) → `runner.py` (execution) → `app.py` (routes) → `static/*` (UI) → quickstart run.

### Parallel opportunities

- T005 alongside T001–T004 (different file).
- In US2: T020 (`pipeline.py`), T021 (`archive.py`) and T027 (`archive.html`) touch three different files with no shared incomplete dependency.
- US3 alongside US2 once US1 is done.
- T034 (`session.html`) alongside T032–T033 once the contract is fixed.
- T038, T039 and T040: three docs files.

## Parallel Example: User Story 2

```text
# Once US1 is done, start these together:
Task: "T020 [US2] join_reels + _probe_reel in pipeline.py"
Task: "T021 [US2] archive_session + sidecar kind in archive.py"
Task: "T027 [US2] Session badge + video list in static/archive.html"
# Then, sequentially:
T019 (sessions.py completion) → T022 (runner join) → T023 (recover/active) → T024 (route) → T025/T026 (UI) → T028 (verify)
```

## Implementation Strategy

### MVP first (US1 only)

1. Foundational T001–T009.
2. US1 T010–T018.
3. **Stop and validate** with quickstart 1–3 and 6. The user can already queue up to 10 videos and walk away. Each reel lands in the archive and the queue survives a redeploy. Sessions simply never close until US2.

### Incremental delivery

1. Add US2: auto-completion and the joined reel, which is the feature's headline output. Validate steps 4, 8 and 9.
2. Add US3: the multi-device chooser. Validate step 7.
3. Add US4: removal and discard. Validate steps 5, 10 and 11.
4. Polish: docs, the canvas measurement, and container verification. **Do not consider the feature shipped before T037 and T041.** The canvas policy and the container ffmpeg are the two things that cannot be settled on the development Mac.

## Notes

- Work on the branch `003-session-video-queue`. CI publishes an image only for pushes to `main`, so checkpoint commits on the branch never reach production.
- **Merge to `main` only after T036–T040.** The README, HANDOFF and compose comment then change in the same change as the behaviour they describe (constitution, Development Workflow).
- Breaking change: the old `POST /api/jobs` flow is gone after T008. Between T008 and T016 the UI cannot submit anything. That is acceptable on the branch.
