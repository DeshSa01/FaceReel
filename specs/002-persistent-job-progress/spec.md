# Feature Specification: Persistent Job Progress

**Feature Branch**: `002-persistent-job-progress`

**Created**: 2026-09-06

**Status**: Draft

**Input**: User description: "when a video is being processed, it should continue processing while the user can navigate to the archive and be able to watch videos from the archive. the video processing progress should also be visible at the bottom of the screen at all times. Additionally, when a video is being processed and user closes the browser window itself, processing should still be unaffected and continue on server side and should be visible and progress synced when user comes back to page while the processing is still in progress on server side."

## Context

Making a reel takes minutes. Today that time is a dead end: the page that submitted
the video is the only thing that knows a reel is being made, so the moment the user
navigates to the archive or closes the window, that knowledge is gone. The work
itself keeps running out of sight, but the user has no way to see it, no way to get
back to it, and no signal when it finishes.

The result is that a user who wants to watch an old reel while waiting for a new one
has to choose between the two, and a user who closes the window has no idea whether
anything is still happening.

This feature separates *the work* from *the window watching it*. The application
becomes the authority on what is being processed, and every page asks it. Waiting
stops being a state the user has to sit still in.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Reconnect to a reel that is still being made (Priority: P1)

A user submits a video and closes the browser window. Some minutes later they open
the application again. The page tells them, immediately and without being asked,
that their reel is still being made and how far along it is — the real current
progress, not a stale number from before they left.

**Why this priority**: This is the foundation. Once any freshly loaded page can
discover the reel in progress on its own, every other part of the feature becomes
possible, and the worst outcome today — a user with no idea whether their reel
survived — is eliminated on its own.

**Independent Test**: Submit a video, close the browser entirely, reopen the
application, and confirm the page shows live progress that continues to advance and
matches what the application has actually done.

**Acceptance Scenarios**:

1. **Given** a reel is being processed, **When** the user closes the browser window and reopens the application, **Then** the page shows that a reel is being processed, with its current stage and percentage, without the user re-entering anything.
2. **Given** a reel is being processed, **When** the user reloads the page repeatedly, **Then** each reload shows the progress that has actually been reached, never a value that goes backwards or restarts at zero.
3. **Given** no reel is being processed, **When** the user opens the application, **Then** no progress is shown and the generator is ready to accept a new video.
4. **Given** a reel finished while the user had no browser open, **When** the user returns, **Then** nothing is shown as in progress and the finished reel is available in the archive.

---

### User Story 2 - Watch the archive while a reel is being made (Priority: P2)

A user submits a video and, rather than waiting on a progress bar, goes to the
archive and plays a reel they made last week. Processing carries on untouched, and a
progress indicator stays pinned to the bottom of the screen the whole time, on the
archive page just as on the generator page.

**Why this priority**: This is the request in its most visible form — the waiting
time becomes usable. It depends on US1 having made the reel discoverable from a page
load, but delivers value the moment it lands.

**Independent Test**: Submit a video, navigate to the archive, play an archived reel
end to end, and confirm both that the progress indicator is visible and advancing at
the bottom of the archive page and that the new reel completes normally.

**Acceptance Scenarios**:

1. **Given** a reel is being processed, **When** the user navigates from the generator to the archive, **Then** processing continues unaffected and the progress indicator remains visible at the bottom of the archive page.
2. **Given** a reel is being processed and the user is on the archive page, **When** the user plays an archived reel, **Then** playback works normally and progress continues to advance.
3. **Given** a reel is being processed, **When** the user navigates back from the archive to the generator, **Then** the indicator is still present and shows the same progress, and the generator does not offer to start a second reel.
4. **Given** a reel is being processed, **When** the user opens the archive page directly without visiting the generator first, **Then** the progress indicator is present.
5. **Given** a reel is being processed, **When** the user scrolls to the bottom of a long archive listing, **Then** the indicator does not hide or block any reel, control, or content.

---

### User Story 3 - Learn the outcome wherever you are (Priority: P3)

The reel finishes while the user is three pages away, watching something else. The
indicator changes to say so and offers a way to get to the new reel. If it failed
instead, it says that, and why.

**Why this priority**: Without this, a user who takes advantage of US2 has to keep
checking the bar to notice a number reaching 100. It completes the feature but the
preceding stories are usable without it.

**Independent Test**: Submit a video, move to the archive, wait for completion, and
confirm the indicator reports the finished reel and leads to it.

**Acceptance Scenarios**:

1. **Given** a reel is being processed and the user is on the archive page, **When** processing completes, **Then** the indicator reports completion and offers a way to reach the finished reel.
2. **Given** a reel is being processed, **When** processing fails, **Then** the indicator reports the failure along with the reason, on whichever page the user is on.
3. **Given** the indicator is reporting a completed or failed reel, **When** the user acknowledges it, **Then** it clears and does not return for that reel.
4. **Given** a reel completed and was acknowledged, **When** the user reloads the page, **Then** no completion notice reappears.
5. **Given** a reel is being processed, **When** the user is on the generator page at the moment it completes, **Then** the existing result view still appears as it does today.

---

### Edge Cases

- **The application restarts while a reel is being made.** Redeploys happen on every published image, and an interrupted reel cannot be resumed. The page MUST say the reel did not finish rather than leaving a bar frozen partway. A stuck indicator is worse than an honest failure, because the user will wait on it indefinitely.
- **Two windows open at once.** Both show the same reel and the same progress; neither can start a second reel while the first is running.
- **The application becomes unreachable mid-reel** (network drop, server restarting). The indicator says the figure it is showing is no longer live, and returns to live updates by itself once contact is restored — without the user reloading.
- **The user tries to submit a second video while one is being processed.** This is already refused; the indicator makes the reason visible before the attempt rather than after.
- **A reel completes with nobody watching.** The reel is archived as normal; the next page load shows nothing in progress and the reel is in the archive.
- **The user acknowledges a failure and immediately submits again.** The new reel is accepted and the indicator tracks it from zero.
- **Playback and processing compete for the machine.** The host is a modest four-core box already saturated by encoding; playing an archived reel while processing MUST NOT fail, though either may be slower.
- **A very long stage with no visible movement** (a long download, a long encode). The indicator continues to name the current stage so the user can tell the difference between slow and stuck.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The application MUST process a submitted video to completion regardless of whether the page that submitted it stays open, is navigated away from, or is closed.
- **FR-002**: The application MUST be able to tell any freshly loaded page whether a reel is currently being processed, and its stage, percentage complete, and status message, without that page supplying an identifier it remembered from a previous visit.
- **FR-003**: Every page of the application MUST show a progress indicator anchored to the bottom of the screen, visible without scrolling, at all times while a reel is being processed.
- **FR-004**: The progress indicator MUST reflect a change in progress within 2 seconds of that change.
- **FR-005**: Users MUST be able to move between the generator and the archive, in either direction and any number of times, while a reel is being processed, without interrupting, restarting, or slowing it.
- **FR-006**: Users MUST be able to browse, open, and play archived reels while a reel is being processed.
- **FR-007**: On returning after any absence, the indicator MUST show the progress the application has actually reached, never a value carried over from before the user left.
- **FR-008**: When processing completes, the indicator MUST report completion and offer a way to reach the finished reel from whichever page the user is on.
- **FR-009**: When processing fails, the indicator MUST report the failure and its reason on whichever page the user is on.
- **FR-010**: The indicator MUST clear when the user acknowledges a completed or failed reel, and MUST NOT reappear for that reel on subsequent visits.
- **FR-011**: When no reel is being processed, no indicator is shown and no space is reserved for one.
- **FR-012**: When the application has no record of a reel a page believed was being processed, that page MUST report that the reel did not finish, rather than continuing to show its last known progress.
- **FR-013**: Every open window MUST show the same reel at the same progress, within the update interval of FR-004.
- **FR-014**: While a reel is being processed, the generator MUST make it evident that another video cannot be submitted until the current one finishes.
- **FR-015**: If the application becomes unreachable while a reel is being processed, the indicator MUST show that the figure displayed is no longer live, and MUST resume live updates automatically once the application is reachable again, without a reload.
- **FR-016**: The indicator MUST NOT cover or block any content or control on the page beneath it; everything on a page MUST remain reachable while the indicator is shown.
- **FR-017**: A reel that completes while no window is open MUST be present in the archive, retrievable and playable, the next time the user visits.
- **FR-018**: The indicator MUST name the stage currently being worked on, so that a slow stage is distinguishable from a stalled one.

### Key Entities

- **Active reel job**: the single reel being processed at any moment. Carries its identity, the stage it is in, how far along it is, a human-readable status message, the tuning values it was started with, and — once it ends — whether it succeeded or failed and why. At most one exists at a time.
- **Progress indicator**: the always-visible representation of the active reel job, present on every page. It is in exactly one of: absent (nothing being processed), processing, stale (contact lost), completed, or failed.
- **Acknowledgement**: a record, held per browser, of which finished or failed reel the user has already been told about, so that a terminal notice is shown once and does not follow them forever.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of reels submitted complete successfully when the user navigates away, plays archived reels, or closes the browser during processing — indistinguishable in outcome from a reel watched to the end.
- **SC-002**: After reopening the application, a user sees the true current progress of an in-flight reel within 2 seconds of the page appearing, with no action on their part.
- **SC-003**: Progress is visible on 100% of pages, without scrolling, for 100% of the time a reel is being processed.
- **SC-004**: An archived reel begins playing within 3 seconds of being opened while another reel is being processed.
- **SC-005**: Zero finished reels go unreported: every reel that completes while the user is elsewhere or absent is either announced by the indicator or present in the archive on their return.
- **SC-006**: A reel that cannot finish because the application restarted is reported as unfinished within 5 seconds of the user's next page load; no indicator ever remains frozen at a partial figure.
- **SC-007**: A user waiting on a reel can start watching an archived one in under 10 seconds and 3 interactions from the moment they submit.

## Assumptions

- **One reel at a time remains the rule.** The application already makes one reel at a time and refuses a second submission while one is running. "The reel being processed" is therefore always at most one, and no queue, ordering, or per-person scoping is required. Letting reels queue up would be a separate feature.
- **Resuming an interrupted reel is out of scope.** A reel cut off by an application restart cannot be picked up partway; it would have to be started again from the beginning. This feature's obligation is to report that honestly (FR-012), not to survive it. Making reels restart-proof would be a separate feature.
- **Notification stays inside the application.** Completion is reported through the on-screen indicator only. Browser notifications, email, and push are out of scope.
- **Finished reels are already durable.** The archive feature persists every completed reel independently of any browser session, so FR-017 depends on existing behaviour rather than adding storage.
- **Single user on a trusted network.** There is no notion of whose reel is being processed; the active reel is the same for everyone who opens the application. This matches the deployment and is assumed throughout.
- **Roughly one-second progress granularity is acceptable.** Users tolerate progress that is up to 2 seconds stale (FR-004); the feature does not require instantaneous updates.
- **The existing generator result view is retained.** When a reel finishes with the user on the generator page, they see the result exactly as they do today; the indicator adds a path to that result from elsewhere rather than replacing it.
- **Existing tuning controls, archive browsing, and deletion are unchanged.** This feature adds visibility and continuity; it changes nothing about how reels are made or stored.
