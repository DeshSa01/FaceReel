# Feature Specification: Session Video Queue

**Feature Branch**: `003-session-video-queue`

**Created**: 2026-10-10

**Status**: Draft

**Input**: User description: "Session management. When the application starts up or loads, present a UI to either join an existing session running on the server side or create a new session; if no sessions are running, the user can create a new session for adding videos to process. Within a session, multiple videos can be added: while one video is being processed, another video can be added to the queue and will be processed after the current one finishes. There is a hard limit of 10 videos per session queue. Once all videos in a session are processed, all the output clips are joined into a single video output file for the session, identified by the session id."

## Context

Today FaceReel makes one reel from one video, and refuses a second submission until
the first is finished. A user who wants the same person's appearances across several
videos has to submit each one, wait out each one, and then has a pile of separate
reels with no way to combine them.

Making a reel takes minutes, so the refusal is the expensive part: the user has to
come back at the right moment to submit the next video, or the machine sits idle.

This feature introduces a **session**: a server-side container the user opens,
adds up to ten videos to, and walks away from. The application works through the
queue one video at a time, and when the session is done it joins every video's
clips into one reel for the whole session, findable by the session's id.

The one-video-at-a-time rule on the machine does not change. What changes is that
the *user* no longer has to enforce it by waiting.

## Clarifications

### Session 2026-10-10

- Q: When is a session complete and ready to be joined into one video? → A: When its queue empties — at least one video has been added and none is waiting or processing. There is no explicit "finish" action.
- Q: Which inputs are set once per session, and which for each video? → A: Every input (link, screenshot, tuning) is per video; the add-video form is prefilled with the previous video's screenshot and tuning.
- Q: Can several sessions run at the same time? → A: Yes, any number; all sessions share one application-wide line, processed one video at a time. *(Ordering revised below.)*
- Q: What should happen to a running session if the application restarts? → A: Sessions and their queues survive the restart; the video that was interrupted starts over from the beginning, and waiting videos carry on.
- Q: In what order does the shared line serve videos from different sessions? → A: By session: the session created first has all its waiting videos processed before a later session's, so it finishes and produces its reel first. Within a session, videos run in the order added. A video already processing is never interrupted. *(Revised after first use, 2026-10-10. The original answer was "in the order videos were added, regardless of session", which let a later session's video run while an earlier session sat idle.)*

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Queue several videos in one session (Priority: P1)

A user opens FaceReel. No sessions are running, so the page offers to start one.
They start a session and add a video. While that video is being processed, they add
a second and a third. Each waits its turn and is processed automatically after the
one before it, without the user returning to submit it.

**Why this priority**: This is the core of the request: the waiting stops being the
user's job. On its own, even without the final joined reel, it already removes the
"come back and resubmit" chore, because each video's reel still lands in the archive.

**Independent Test**: Create a session, add three videos in quick succession, close
the browser, and come back after they would all have finished. Confirm each was
processed in the order added and each produced a reel.

**Acceptance Scenarios**:

1. **Given** no sessions exist, **When** the user opens the application, **Then** they are offered only the option to create a new session.
2. **Given** a newly created session with an empty queue, **When** the user adds a video, **Then** processing of that video starts without further action.
3. **Given** a session is processing a video, **When** the user adds another video, **Then** it is accepted, shown as waiting in the queue with its position, and the current video's processing is unaffected.
4. **Given** a session has a video processing and two waiting, **When** the processing video finishes, **Then** the next waiting video (in the order added) starts automatically.
5. **Given** a session already holds 10 videos that have not been removed, **When** the user tries to add another, **Then** the addition is refused with a message stating the 10-video limit, and nothing already in the session is affected.
6. **Given** a session has videos waiting, **When** the user closes the browser, **Then** the queue continues to be worked through on the server.
7. **Given** a session's last video is processing and nothing is waiting, **When** the user views the session, **Then** they are told the session will complete and be joined when this video finishes, unless they add another first.
8. **Given** an add-video form for a session that already has a video, **When** the user opens it, **Then** the screenshot and tuning are prefilled from the most recently added video, and the link is empty.

---

### User Story 2 - Get one joined reel for the whole session (Priority: P2)

When the last video in a session finishes and nothing is left waiting, the session is
complete. The application joins the reels of all its videos, in the order the videos were added, into a single video for the session.
The user can watch and download it, and find it later by its session id.

**Why this priority**: This is the payoff the user described: one output per session.
It depends on US1 having produced the per-video results to join.

**Independent Test**: Create a session with two short videos, let both finish, and
confirm one video is produced whose length equals the sum of the two
per-video reels, whose footage appears in the order added, and which is retrievable
by the session id.

**Acceptance Scenarios**:

1. **Given** a session with at least one video, **When** its last video finishes and nothing is waiting, **Then** the session stops accepting videos and the reels of every successfully processed video are joined, in the order the videos were added, into one video for the session.
2. **Given** a session's joined video has been produced, **When** the user looks it up by the session id, **Then** they can play and download it.
3. **Given** a session in which one video failed and others succeeded, **When** the session is joined, **Then** the joined video contains the successful videos' footage only, and the session's summary names the video that failed and why.
4. **Given** a session in which every video failed or found no appearances, **When** the session ends, **Then** no joined video is produced and the session reports that there was nothing to join.
5. **Given** a session's videos were made at different resolutions, **When** they are joined, **Then** the joined video plays continuously from start to end with no failed or garbled section at the transitions.
6. **Given** the application restarts after a session's joined video was produced, **When** the user looks it up by the session id, **Then** it is still available.

---

### User Story 3 - Join a running session from any browser (Priority: P3)

A user created a session on their laptop and queued four videos. Later, on their
phone, they open FaceReel. The page lists the session that is running, with enough
detail to recognise it, and lets them join it to see its queue and progress and add
more videos.

**Why this priority**: It makes the session a server-side thing rather than a
browser-tab thing, which is what the user asked for. US1 and US2 deliver value from a
single browser without it.

**Independent Test**: Create a session in one browser and add a video. Open the
application in a second browser, confirm the session is listed, join it, and add a
second video from there. Confirm both browsers show the same queue.

**Acceptance Scenarios**:

1. **Given** one or more sessions are running, **When** the user opens the application, **Then** they are shown the running sessions and an option to create a new one.
2. **Given** a running session is listed, **When** the user joins it, **Then** they see every video in it with its state (waiting, processing with progress, done, failed), and can add videos to it up to the limit.
3. **Given** two browsers have joined the same session, **When** a video is added from one, **Then** the other shows it in the queue within the normal progress update interval.
4. **Given** a session has ended, **When** the user opens the application, **Then** that session is no longer offered to join, and its joined reel is reachable from the archive.

---

### User Story 4 - Manage what is waiting (Priority: P4)

A user notices they queued the wrong video. While it is still waiting, they remove
it. It never gets processed and does not count toward anything in the joined reel.

**Why this priority**: A convenience. Without it, the remedy is to let the wrong
video run, which costs machine time but nothing else.

**Independent Test**: Queue three videos, remove the third while it is waiting, and
confirm it is never processed and is absent from the session's joined video.

**Acceptance Scenarios**:

1. **Given** a video is waiting in a session queue, **When** the user removes it, **Then** it leaves the queue, is never processed, and the remaining videos keep their relative order.
2. **Given** a video is currently processing, **When** the user views it, **Then** no option to remove it is offered.

---

### Edge Cases

- **The queue drains before the user has added everything.** A user adds video 1, it finishes in four minutes, and they meant to add video 2 five minutes later. By then the session is complete and joined (FR-011). This is the chosen behaviour: video 2 goes into a new session. The warning in US1 scenario 7 exists so this is never a surprise.
- **A session is created but no video is ever added.** An empty session is not complete — completion needs at least one video — so it stays open and listed until a video is added or the user discards it (FR-024).
- **The user removes the last waiting video while nothing is processing for the session.** The session's queue is now empty, so it completes and is joined from what has already finished.
- **The 10-video limit is reached through removals.** Whether a removed waiting video frees its slot. Assumed yes: the limit counts videos in the session, and a removed video is no longer in it.
- **Two sessions both have work waiting.** The machine still processes one video at a time across the whole application. The older session's videos all go first (FR-010), so a newer session waits until the older one has nothing waiting. The queue position shown to a user MUST reflect the real wait, not only their own session's queue, and MUST say when the wait is for another session.
- **A video is added to an older session while a newer session has videos waiting.** It goes ahead of the newer session's waiting videos, but behind the video currently processing.
- **The application restarts mid-session.** Redeploys happen on every published image. Sessions resume (FR-020): the video that was processing starts over from the beginning, and its earlier partial progress is discarded. A session that was in the middle of being joined starts its join over.
- **The application restarts repeatedly while the same video is processing.** Each restart starts that video over; it is not marked failed for having been interrupted.
- **A video's reel fails to join** (for example, it is corrupt). The joining step reports the failure for the session rather than producing a truncated video presented as complete.
- **A video finds no appearances of the person.** It ends `failed` with the "not found" reason, as the pipeline reports it today. It contributes nothing to the joined reel, and the session's summary names it.
- **Joining takes time.** Joining up to ten reels is itself work on a machine where encoding is the bottleneck. The session shows that it is being joined, with progress, so a long join is distinguishable from a stall.
- **The same video is added twice.** Allowed: it may be intentional (for example, with different settings). No deduplication.
- **A video is added to a session that is being joined or has ended.** Refused with a message; the user is offered a new session.
- **Disk fills during a long session.** The failing step reports the failure; reels already produced are not removed.

## Requirements *(mandatory)*

### Functional Requirements

**Sessions**

- **FR-001**: On every load of the application's main page, the user MUST be presented with the running sessions they can join and an option to create a new session. When no sessions are running, only the create option is offered.
- **FR-002**: Each session MUST have a unique identifier, assigned at creation, that is shown to the user and is used to find the session's joined video afterwards.
- **FR-003**: Each listed running session MUST show enough to recognise it: its identifier, when it was created, how many videos it holds and in what states, and the title of at least its first video once known.
- **FR-004**: Sessions MUST live on the server: a session continues to exist and progress regardless of whether any browser has it open, and any browser may join it.
- **FR-005**: The application MUST allow any number of running sessions at a time. All sessions share the single application-wide line (FR-010).

**Queue**

- **FR-006**: Users MUST be able to add a video to a session at any time while the session is accepting videos, including while another video in it is processing.
- **FR-007**: Each video added MUST specify its own source link, screenshot of the person, and tuning (zoom, 4K, clip fine-tuning). After the first video, the form MUST be prefilled with the screenshot and tuning of the session's most recently added video, so that adding another video of the same person needs only a new link.
- **FR-008**: A session MUST hold at most 10 videos. An attempt to add an 11th MUST be refused with a message stating the limit, and MUST NOT affect the session.
- **FR-009**: Videos within a session MUST be processed one at a time, in the order they were added.
- **FR-010**: Across the whole application, at most one video MUST be processing at any moment. When several sessions have waiting videos, they MUST be served session by session, in the order the sessions were created; within a session, in the order its videos were added. A video already processing MUST NOT be interrupted, so a video added to an older session waits only for the video in progress.
- **FR-011**: A session MUST become complete at the moment it holds at least one video and none of its videos is waiting or processing. On completion it MUST stop accepting videos and be joined (FR-018). There is no separate user action to end a session.
- **FR-011a**: While a session's only remaining video is processing, the session view MUST warn that the session will complete when that video finishes unless another video is added first.
- **FR-012**: Users MUST be able to remove a video that is waiting and has not started. A removed video MUST NOT be processed and MUST NOT appear in the joined reel.
- **FR-013**: A video that is processing MUST NOT be removable or cancellable through this feature.
- **FR-014**: When a video fails, the session MUST record the reason and continue with the next waiting video.

**Visibility**

- **FR-015**: A user who has joined a session MUST see each of its videos with its state — waiting (with its position in the application-wide line), processing (with stage and percentage), done (with its clip count and footage length), failed (with reason), or removed — updated within 2 seconds of a change.
- **FR-016**: The always-visible progress indicator from the persistent-progress feature MUST continue to work on every page, and MUST identify which session and which video within it (for example, "Session 4f2a… · video 2 of 5") is being processed.
- **FR-017**: While a session is being joined, its state MUST say so, with progress, as a distinct step after the last video.

**Joined output**

- **FR-018**: When a complete session has at least one successfully processed video with footage, the application MUST join those videos' reels, in the order the videos were added, into a single video for the session, which plays continuously even when the inputs differ in resolution.
- **FR-019**: The session's joined video MUST be retrievable by its session identifier, MUST be playable and downloadable, and MUST survive an application restart. It MUST appear in the archive, distinguishable from single-video reels.
- **FR-020**: Sessions, their queues, and every queued video's inputs MUST survive an application restart. After a restart, the video that was processing MUST start over from the beginning, waiting videos MUST continue in their original order, and a session that was being joined MUST restart its join. Being interrupted by a restart MUST NOT mark a video as failed.
- **FR-021**: Each successfully processed video MUST also continue to produce its own reel in the archive, as today, so that a failure to join never loses the individual results.
- **FR-022**: If joining fails, the session MUST be reported as failed to join, with the reason, and every individual reel MUST remain available.

**Identifiers and safety**

- **FR-024**: Users MUST be able to discard a session to which no video has ever been added. A session with videos cannot be discarded through this feature.
- **FR-023**: Any session identifier received from outside the application MUST be validated against the identifier format before it is used to locate anything on disk.

### Key Entities

- **Session**: a server-side container for up to 10 videos. Has an identifier, a creation time, a state (open, joining, finished, nothing to join, failed to join), an ordered list of queued videos, and — once finished — one joined video.
- **Queued video**: one entry in a session. Has its position (order added), source link, the screenshot and tuning it will be processed with, a state (waiting, processing, done, failed, removed), its progress while processing, and on completion a link to its individual reel or the reason it failed.
- **Joined reel**: the single video produced for a finished session, identified by the session identifier, built from the individual reels of its successful videos in order. Durable, and listed in the archive with the session's videos it was built from.
- **Application-wide line**: the single order in which waiting videos from every session are processed, one at a time.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can queue 10 videos in one session without ever waiting for a video to finish before adding the next; all 10 are accepted within 5 minutes of the session being created.
- **SC-002**: The machine sits idle for no more than 5 seconds between one queued video finishing and the next starting.
- **SC-003**: 100% of sessions with at least one successful video produce exactly one joined video, whose footage length equals the sum of its constituent reels within 1 second, in the order added.
- **SC-004**: A session's joined video is found by its session identifier in under 10 seconds, including after an application restart.
- **SC-005**: A user opening the application on a second device can find and join a running session in under 3 interactions.
- **SC-006**: The 11th addition to a session is refused 100% of the time, with nothing in the session changed.
- **SC-007**: After an application restart, 100% of open sessions resume: the interrupted video restarts and every waiting video is processed, with no user action.
- **SC-008**: A failure in one video never prevents the remaining videos in the session from being processed.

## Assumptions

- **Single user on a trusted network.** Any visitor can see and join any running session; there are no accounts, ownership, or permissions on sessions. This matches the deployment.
- **The machine still does one video at a time.** The host is a four-core machine already saturated by encoding (constitution, Runtime & Deployment Constraints). Sessions add queueing, not parallelism.
- **The 10-video limit counts videos in the session, not attempts.** Failed videos count; removed videos do not.
- **Join order is the order videos were added.** Reordering a queue is out of scope.
- **Cancelling a video that is already processing is out of scope.** It is a change to the pipeline, not to queueing.
- **Joined reels are subject to the same archive deletion as single reels.** Deleting a session's joined reel from the archive does not delete its individual reels, and vice versa.
- **Ended sessions are not re-opened.** Adding more videos after a session ends means creating a new session.
- **Resuming an interrupted video partway is out of scope.** A video cut off by a restart starts again from the beginning (FR-020); only the session and its queue are restart-proof, not an individual video's progress.
- **Sessions complete on their own.** Because a session completes as soon as its queue empties (FR-011), a user who wants many videos in one session adds them while earlier ones are still processing.
- **Supersedes parts of the persistent-progress feature (002).** Progress may restart at 0% after a restart (replaces 002 FR-007 across restarts). The terminal notice is per session, not per reel (002 FR-008). A restart re-queues work instead of reporting it unfinished (002 FR-012). Submitting while a video processes is now allowed (002 FR-014). All other 002 requirements stand.
- **The generator form's existing inputs (link, screenshot, zoom, 4K, clip fine-tuning) are reused** for adding a video to a session; this feature changes where they are submitted, not what they are.
