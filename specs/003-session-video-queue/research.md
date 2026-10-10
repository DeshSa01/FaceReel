# Phase 0 Research: Session Video Queue

No `NEEDS CLARIFICATION` markers reached this phase. The four that mattered (completion trigger, per-video inputs, concurrent sessions, restart behaviour) were settled in the spec's Clarifications on 2026-10-10. What follows is the design reasoning and the alternatives rejected.

One observation shapes the whole design: **today's concurrency model is "one thread per job, refuse if busy"**. `create_job` starts a fresh daemon thread per submission and relies on a 409 to keep the machine at one video at a time. A queue inverts that: submissions are always accepted, and *something else* decides when each one runs. That something is the new piece, and almost every decision below is about making it survive a restart.

## D1. A durable session store, outside `storage/jobs/`

**Decision**: Each session is one directory, `storage/sessions/<sid>/`, holding `session.json` (the session and its ordered videos) and `screenshots/<vid>.<ext>`. `session.json` is rewritten whole, atomically (write `session.json.tmp`, then `os.replace`), on every *state transition*: session created, video added, video started, video finished/failed/removed, session completed, join finished. Per-tick progress (stage, percentage, message) is **not** persisted. It stays in memory.

**Rationale**:
- FR-020 requires the queue and every queued video's inputs to survive a restart. The only durable location is `storage/` (constitution, Runtime & Deployment Constraints). `storage/jobs/` is wiped at every start, so it cannot be used. The sibling placement mirrors the reasoning `archive.py` records for `storage/archive/`: `clean_jobs_dir()` stays correct by never having to learn about it.
- `os.replace` is atomic on one filesystem, so a crash mid-write leaves either the old or the new `session.json`, never a torn one. This is the same guarantee `archive_job` gets from its staging rename.
- Progress ticks happen several times a second during a scan. Writing them to disk would add I/O to a machine whose bottleneck is already disk-heavy encoding, and it would buy nothing: FR-020 restarts an interrupted video from zero anyway.

**Alternatives rejected**:
- *SQLite.* No new package is needed (it ships with Python), but a single-writer, single-process app with at most a few dozen live records gains nothing from a query engine. It would make the on-disk state opaque to `cat`, which is how this app has been debugged so far.
- *One global `sessions.json`.* Every write would rewrite every session, and one corrupt file would lose them all. One file per session also matches the archive's one-directory-per-entry layout.
- *Keep state in memory, like `jobs`.* This was option B in the clarification and was rejected there: every push to `main` redeploys.

## D2. One long-lived runner thread pulling from an application-wide line

**Decision**: Replace the per-job `threading.Thread` with a single runner thread, started in `lifespan` and parked on a `threading.Condition`. Its loop, under the store lock:

1. If any session is in `joining`, run the oldest join (by `completed_at`).
2. Otherwise take the first waiting video in queue order, `(session created_at, session id, video seq)`, and mark it `processing`. *(Revised 2026-10-10: originally the lowest global `seq`. See the note below.)*
3. Otherwise `wait()` on the condition until an add, removal, or recovery calls `notify()`.

The pipeline and ffmpeg calls run **outside** the lock. Only the state transitions run under it.

**Rationale**:
- FR-010 requires at most one video processing application-wide, served in the order added regardless of session. A single consumer satisfies this by construction. Today's 409 check *enforces* the rule. A single consumer makes breaking it impossible.
- Within a session, a global monotonic `seq` (max on disk + 1, assigned at add time) defines "the order added" without relying on wall-clock time, which can step backwards (NTP, a container clock change). Between sessions, the session's `created_at` decides. It is parsed rather than compared as text, because the UTC offset in it changes across DST. A clock step could misorder two sessions created moments apart, which is acceptable for a single user.

**Ordering revised after first use (2026-10-10).** Pure add order across sessions let a newer session's video run while an older session sat idle. Removing the older session's waiting videos then looked like it changed nothing, because its next video was still behind the newer session's earlier-added one. The user's model is "the session started first finishes first", so ordering is now by session, then by add order. Processing is still never pre-empted.
- SC-002 allows at most 5 seconds of idle between videos. The condition variable makes the hand-off immediate rather than polled.
- Starting the thread in `lifespan` rather than at import follows the precedent `clean_jobs_dir()` records: importing the module must not have side effects.

**Joins go before waiting videos.** A completed session's inputs are all ready, its user is waiting for exactly that output, and a join costs far less than processing a video (D5: usually a stream copy). Putting joins in the video line would let one long session's join wait behind ten videos that another session added later.

**Alternatives rejected**:
- *A thread per session.* Would break FR-010 unless the threads coordinated through a shared lock, which rebuilds the single consumer with more moving parts.
- *`queue.Queue`.* It cannot remove a waiting item (FR-012) or report positions (FR-015), and it does not survive a restart. The authoritative line has to be the persisted session records, and a second in-memory copy would only drift from them.
- *Round-robin across sessions.* Offered in clarification and declined.
- *Strict add order across sessions.* The original choice. Replaced as described above.

## D3. Restart recovery reconciles against the archive

**Decision**: In `lifespan`, after `clean_jobs_dir()` and before the runner starts, load every `storage/sessions/*/session.json` and repair it:

- A video in `processing`: if `storage/archive/<vid>/` already exists, mark it `done`. The process died after `archive_job`'s rename but before the session write. Otherwise reset it to `waiting`, keeping its `seq`, so it stays first in line.
- A session in `joining`: if `storage/archive/<sid>/` exists, mark it `finished`. Otherwise leave it in `joining`; the runner retries the join.
- A session in `open` whose videos are all terminal, and which has at least one video: mark it complete and move it to `joining`. This covers the completion check being lost to a crash.

A file that fails to parse is logged and skipped, never deleted.

**Rationale**: The first crash window sits between two durable writes (`archive_job`'s rename, then the `session.json` write). Without the archive check, a restart in that window would re-run the video, and `archive_job`'s `os.rename` would then fail because the final directory already exists. That would mark the video as failed even though its reel exists. Using the archive as the tiebreaker makes recovery idempotent. Skipping unparseable files rather than deleting them is the same choice `read_entry` made for the archive (Constitution Principle V: never delete as a side effect).

**A second window**: inside `archive_job`/`archive_session`, between `os.makedirs(staging)` and the final rename. A crash there leaves `archive/.tmp-<id>/`. Because `makedirs` has no `exist_ok`, the retried video would then fail with `FileExistsError`, and FR-020 forbids marking it failed for that. Recovery therefore removes every `archive/.tmp-<id>` whose `<id>` passes `valid_id`. That is the only case where a staging directory can be stale, since nothing else is in flight at start-up. It is an automatic deletion confined to `ARCHIVE_DIR`, so the README must document it (Principle V).

**A retried session's re-join** (FR-025) adds two cases. (1) The archive still holds the session's *earlier* reel while the new join runs, so recovery only accepts a reel created at or after the session's `completed_at`. (2) `archive_session` replaces an existing entry by parking it as `.old-<sid>`, renaming the new one in, then deleting the parked one. At start-up, `recover_parked` restores a parked reel that has no entry, and deletes one whose replacement landed.

**Restart-safe inputs**: The runner **copies** the video's screenshot from the session directory into the job's scratch directory before calling `process_job`. `archive_job` already *moves* the screenshot into the archive. Without the copy, it would move it out of the session store, and a crash after that would leave a waiting video with no screenshot. The copy also keeps the original available as a prefill source (D7). `archive.py` needs no change for this.

## D4. Completion is checked at every transition that can empty a queue

**Decision**: A function `_maybe_complete(session)` runs under the lock after a video finishes, after it fails, and after a waiting video is removed. If the session is `open`, has at least one video, and none of its videos is `waiting` or `processing`, it sets `joining`, stamps `completed_at`, persists, and notifies the runner. `add_video` checks `state == open` under the same lock.

**Rationale**: FR-011 says completion happens at the moment the queue empties. Running the check and the add under one lock removes the race in which a user adds a video in the same instant the last one finishes. Whichever acquires the lock first wins, and the loser gets a clear 409 ("session has completed"), as the spec's edge case requires.

A session with zero videos is never complete (spec edge case), so an empty session waits indefinitely until it gets a video or is discarded (FR-024).

## D5. Joining: stream copy when the reels match, otherwise re-encode all

**Decision**: A new `pipeline.join_reels(paths, work_dir, progress)`:

1. `ffprobe` each reel for width, height, SAR, frame rate, pixel format, and audio presence/rate/channels.
2. **All identical** → concat demuxer with `-c copy` (absolute paths, per the existing comment in `cut_and_stitch`). This takes seconds.
3. **Any difference** → choose a canvas, then re-encode **every** reel to it with the same encoder settings `cut_and_stitch` uses (`libx264 -preset medium -crf 18`, `aac -ac 2 -ar 44100`, `-video_track_timescale 90000`). Use `scale` to fit, `pad` to letterbox, `setsar=1` and `fps`. Generate silent audio for a reel that has none. Then concat-copy the normalised files. Progress advances per reel.

**Canvas**: the most common `(width, height, fps)` among the reels, ties broken by the larger area.

**Rationale**:
- FR-018 requires the joined reel to play straight through even when inputs differ in resolution. The concat demuxer with stream copy takes codec parameters from the first file. Feeding it reels of different sizes produces a file that plays the first reel and then shows garbage or stops, depending on the player. Copy is only safe when the streams genuinely match.
- Most sessions will take the copy path. Prefill (FR-007) carries tuning forward, so a typical session's reels share height and encoder settings. Frame rate is the most likely mismatch, between differently sourced videos.
- **Why re-encode all and not just the odd ones out**: concatenating copied and re-encoded H.264 relies on the SPS/PPS matching across files. Same encoder settings do not guarantee that, since x264 picks the level from resolution and frame rate. Re-encoding everything is slower only in the mixed case and is correct by construction.
- **Why the mode and not the maximum**: one `hi_res` video in an otherwise 1080p session would otherwise force all ten reels to be upscaled and re-encoded at 4K on an N95. That multiplies the work and the file size for no gain in sharpness. Using the mode means the fewest reels change size.

**Principle II note**: canvas choice affects output quality, so it is a quality decision, not just a technical one. There is no measurement yet to justify it. `tasks.md` MUST include measuring join wall-clock time on the deployment host for (a) a 3-reel copy-path session and (b) a 3-reel mixed 1080p/4K session under both canvas policies. The figures go in the comment on the canvas rule. If the measurements contradict this choice, the policy changes.

**Alternatives rejected**:
- *The concat filter (`-filter_complex concat`) over the raw reels.* This is one pass, but it re-encodes even when every reel matches, which loses the copy path's seconds-not-minutes behaviour.
- *Re-running the pipeline across all source videos.* The reels are already in the archive. Re-downloading and re-scanning would multiply the session's cost for an identical result.

## D6. The joined reel is an archive entry keyed by the session id

**Decision**: Session ids use the archive's existing id format, `^[0-9a-f]{12}$`, from `uuid4().hex[:12]`. Creation re-rolls on a collision with any existing session directory *or* archive entry. A finished join goes through a new `archive.archive_session(sid, joined_path, summary)`. This uses the same staging-directory-then-rename pattern as `archive_job`, writes a sidecar with `"kind": "session"` and a `videos` summary, and produces a thumbnail as usual. Single-video sidecars without `kind` are read as `"kind": "video"`, so existing archives need no migration.

`GET /api/sessions/{sid}/output` serves `storage/archive/<sid>/output.mp4`.

**Rationale**:
- FR-019 requires the joined reel to be durable, retrievable by session id, and listed in the archive while distinguishable from single reels. Making it an archive entry gives it durability, thumbnails, the listing, playback, download, and deletion through code that already works and already validates ids.
- One id format means one validator. Constitution Principle V requires validating an id before it reaches a path. Every new route takes `sid` and `vid` through the same `valid_id`, so there is no second regex that could drift.

**Inputs to the join** are each done video's `storage/archive/<vid>/output.mp4`, in session order. A reel the user deleted from the archive before the join is skipped and named in the summary. This follows the spec's assumption that deleting one reel does not affect the other.

## D7. Prefill is server-side

**Decision**: `POST /api/sessions/{sid}/videos` accepts either a `screenshot` upload or `screenshot_from=<vid>`, naming an earlier video in the same session. The server copies that file. `GET /api/sessions/{sid}` returns `prefill: {from_video, tuning}` taken from the most recently added video. The session page shows that screenshot as the default, with a "Use a different screenshot" control, and sets the tuning controls from it.

**Rationale**: A browser cannot set a file input programmatically. And because sessions are joined from other devices (US3), the previous screenshot may never have been on this browser. A server-side reference is the only form of prefill that works in both cases.

## D8. Pages: a chooser at `/`, a session page at `/session/<sid>`

**Decision**:
- `static/index.html` becomes the **session chooser**: open sessions (FR-003 fields) with a Join link each, and a Create button. With no open sessions it shows only Create (FR-001).
- A new `static/session.html` holds the existing generator form, moved from `index.html` (FR-007, last assumption), plus the queue list, the "will complete when this finishes" warning (FR-011a), and the joined-reel player once finished.
- `GET /session/{sid}` validates `sid` (400 when malformed, as `_require_valid_id` does) and serves the page with `no-cache`, like the existing pages.

The session id is in the path, so a session page is bookmarkable and shareable across devices, and reloading it returns to the same session without `localStorage`.

**Alternatives rejected**: *One page that swaps between chooser and session view client-side.* This would need client routing to make the session URL-addressable, and it would make the 341-line `index.html` larger still.

## D9. Polling cadence and the shared progress bar

**Decision**: Keep polling (002 research D2). The session page polls `GET /api/sessions/{sid}` once a second while visible. The chooser polls `GET /api/sessions` every 2 seconds while visible. `progress.js` keeps polling `GET /api/jobs/active`, whose payload gains `kind` (`"video"`/`"join"`), `session_id`, `index` and `total`. The bar's stage line reads e.g. "Session 4f2a91… · video 2 of 5 · Scanning for the person" (FR-016).

The bar's **terminal notice** becomes per session, not per video. When nothing is processing, `active` returns the most recently completed session (finished, nothing to join, or join failed), with a link to `/session/<sid>`. The acknowledgement key holds that session id. A single video finishing inside a busy session does not raise a notice. Per-video outcomes are shown on the session page.

**Rationale**: A notice per video would fire up to ten times per session, and the user would learn to dismiss it unread. The session's outcome is the event the user is actually waiting for.

**Interaction with 002 FR-012** (interrupted reel detection): after this feature, a restart no longer makes the processing item vanish. It comes back as the same id, restarting from 0%. The "watched id vanished" branch in `progress.js` is **removed**. With a queue, `active` changes id at every normal hand-off between videos, so it would fire after every success, and restarts no longer lose work for it to detect. The bar briefly showing a lower percentage after a restart is the honest picture under FR-020.

## D10. The retired single-job API

**Decision**: Remove `POST /api/jobs`, `GET /api/jobs/{job_id}`, `GET /api/jobs/{job_id}/output`, and the module-level `jobs` dict. Keep `GET /api/jobs/active`, reshaped, so `progress.js` keeps its one endpoint.

**Rationale**: Leaving `POST /api/jobs` in place would create a second way to start processing that bypasses the line. That breaks FR-010 the moment anything calls it. There are no external clients (single user, two hand-written pages), so nothing outside this repository depends on these routes. The route-order comment above `/api/jobs/active` becomes obsolete once `/api/jobs/{job_id}` is gone, and is removed with it.

## D11. Limits and removal

- **The 10-video limit** counts the session's videos whose state is not `removed`, checked under the lock in `add_video`. An add over the limit gets 409 with "A session holds at most 10 videos." (FR-008). The figure 10 is a product rule from the user, not a tuning value, so Principle II does not apply. It still gets a named constant, `MAX_VIDEOS_PER_SESSION`, with a comment saying where it came from.
- **Removal** (FR-012/013): `DELETE /api/sessions/{sid}/videos/{vid}` succeeds only for `waiting`, and returns 409 otherwise. The video record stays, as `removed`, so the session's history shows it. Its screenshot stays too, because a later video may have been prefilled from it.
- **Discarding a session** (FR-024): `DELETE /api/sessions/{sid}` succeeds only if the session has never had a video, and returns 409 otherwise. It `rmtree`s `storage/sessions/<sid>` after `valid_id`. This is the feature's only deletion, and it is confined to the validated session directory (Principle V).

## D12. Concurrency inside the process

All session state lives in one `SessionStore` object behind one `threading.Lock`, and the runner's condition is built on that lock. Request handlers return **copies** (`copy.deepcopy` of the records plus runtime progress) built under the lock. They never return live references.

**Rationale**: 002 research D6 found a real `RuntimeError: dictionary changed size during iteration` caused by a handler iterating a dict the worker was mutating. This store has more writers (the runner, adds, removals) and more readers (three polling pages), so the same class of race becomes more likely. Snapshotting under the lock removes the class entirely. A dozen small records cost nothing to copy.

**Single worker remains mandatory** (constitution). Under two uvicorn workers there would be two runners, two in-memory progress maps, and two writers racing on `session.json`. The contract states this.
