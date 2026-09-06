# Feature Specification: Reel Archive

**Feature Branch**: `001-reel-archive`

**Created**: 2026-09-05

**Status**: Draft

**Input**: User description: "We want to implement the ability to store every processed video in a storage folder, so when a user comes back to the FaceReel app he can access all the previous generations. We would want to do this in a separate page accessible from the landing page. This archive page should have the ability to access all the saved videos and also a web player to play the videos from the storage. User can also permanently delete videos from storage."

## Context

Today a finished reel is written into the working directory of the job that produced it, and the record that the job ever happened exists only in the running process's memory. Every time the application starts it deletes all job working directories, because with job records lost there is nothing left that can claim them. That was a reasonable trade when the app was started by hand for one video at a time.

The app now runs continuously on a home server and is restarted whenever it is redeployed or the machine reboots. Under those conditions the current behaviour destroys every reel the user has made. The user must download each reel immediately or lose it.

This feature makes finished reels durable and browsable.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Reels survive a restart (Priority: P1)

A user makes a reel, closes the browser, and comes back the next day after the server has been restarted. The reel they made is still there and still plays.

**Why this priority**: This is the entire point of the feature. Everything else is a way of getting at reels that this story keeps alive. Without it, no other story has anything to show. It is also the only story that changes existing destructive behaviour, so it carries the most risk and should land first.

**Independent Test**: Generate a reel, restart the application, and confirm the reel's file and its recorded details are both still present and unchanged. Delivers durability even before any archive page exists.

**Acceptance Scenarios**:

1. **Given** a job has completed successfully, **When** the application is restarted, **Then** the reel produced by that job is still on disk and still playable.
2. **Given** a job failed or was abandoned midway, **When** the application is restarted, **Then** its leftover working files are cleared, exactly as they are today.
3. **Given** a completed reel exists, **When** the application starts, **Then** the details recorded about that reel (title, when it was made, how it was configured) are readable again without any prior process being alive.

---

### User Story 2 - Browse and play past reels (Priority: P2)

A user opens the archive from a link on the main page and sees every reel they have made, newest first, each with a picture of what it contains. They pick one and watch it in the page.

**Why this priority**: This is how the durability from Story 1 becomes visible. It is the primary way the user interacts with the feature, but it is only meaningful once reels persist.

**Independent Test**: With several archived reels present, open the archive page and confirm each is listed with its recorded details and a representative image, and that each can be played to completion in the browser.

**Acceptance Scenarios**:

1. **Given** the user is on the main page, **When** they look for their past work, **Then** a clearly labelled link takes them to the archive.
2. **Given** several reels have been archived, **When** the user opens the archive, **Then** all of them are listed with the most recently created first.
3. **Given** the archive is listing reels, **When** the user looks at an entry, **Then** they can see a representative still image from that reel, its source video's title, when it was made, how many clips it contains, how long it runs, and the settings it was made with.
4. **Given** the user selects a reel, **When** it opens, **Then** it plays in the page with normal playback controls, including seeking to an arbitrary point.
5. **Given** a reel is open, **When** the user chooses to download it, **Then** they receive the video file under a name that identifies it.
6. **Given** no reels have been archived yet, **When** the user opens the archive, **Then** they are told the archive is empty rather than shown a broken or blank list.

---

### User Story 3 - Delete reels to reclaim space (Priority: P2)

A user with an archive that has grown too large deletes reels they no longer want, and the space is genuinely freed.

**Why this priority**: Equal in priority to browsing, because with unlimited retention this is the only mechanism preventing the disk from filling. A user who cannot delete is a user who eventually cannot generate.

**Independent Test**: Delete an archived reel and confirm its video, image, screenshot and recorded details are all gone from disk, the entry disappears from the list, and the reported total size drops accordingly.

**Acceptance Scenarios**:

1. **Given** the user has chosen to delete a reel, **When** they are asked to confirm, **Then** the reel is only deleted after they confirm, and abandoning the confirmation leaves it untouched.
2. **Given** a deletion is confirmed, **When** it completes, **Then** every file belonging to that reel is removed from storage, leaving nothing behind.
3. **Given** a reel has been deleted, **When** the archive is next viewed, including after a restart, **Then** the deleted reel does not reappear.
4. **Given** a reel has been deleted, **When** the user views the archive, **Then** the reported total size of the archive has decreased by that reel's size.
5. **Given** the archive is displayed, **When** the user views it, **Then** the total space the archive occupies is shown, so growth is visible before it becomes a problem.

---

### Edge Cases

- **A reel's video file is missing but its record remains** (deleted outside the app, or a partial delete): the entry must not break the page. It should be shown as unavailable or omitted, never render a dead player.
- **A record is unreadable or corrupt**: one damaged entry must not prevent every other reel from listing.
- **Two reels come from the same source video**: both are kept as separate entries; a new reel never silently overwrites an older one.
- **The disk is full when a job finishes**: the failure must be reported against that job rather than corrupting the archive or leaving a half-written entry that later renders as broken.
- **A reel is deleted while it is being watched in another browser tab**: playback of the open copy may fail, but the archive itself must stay consistent and the entry must not return.
- **The still image cannot be produced from a reel**: the reel must still be archived and playable; only its picture is absent.
- **A job's own working files are cleared at startup** while an archived copy of its reel exists: clearing working files must never remove archived reels.
- **The user deletes the last remaining reel**: the archive returns to its empty state cleanly.

## Requirements *(mandatory)*

### Functional Requirements

**Archiving**

- **FR-001**: The system MUST archive a reel automatically whenever a job completes successfully, with no user action required.
- **FR-002**: The system MUST NOT archive reels for jobs that fail, error, or never finish.
- **FR-003**: The system MUST keep archived reels in a location that the existing start-up clearing of job working files does not touch.
- **FR-004**: The system MUST keep archived reels and their records on storage that survives both application restart and redeployment of the application.
- **FR-005**: The system MUST continue to clear abandoned job working files at start-up, as it does today.

**What is recorded**

- **FR-006**: For each archived reel the system MUST record the source video's title, the number of clips, the source video's duration, the reel's duration, the reel's resolution, and the number of clips that were reframed.
- **FR-007**: For each archived reel the system MUST record the settings the job ran with: lead-in, boundary reach, clip gap, whether reframing was on, and whether the high-resolution source option was on.
- **FR-008**: For each archived reel the system MUST record the address of the source video.
- **FR-009**: For each archived reel the system MUST retain the reference face image that the job was created from.
- **FR-010**: For each archived reel the system MUST record the date and time it was created.
- **FR-011**: The system MUST store a still image taken from each reel, for use as its visual identifier in the listing.
- **FR-012**: The system MUST be able to read every recorded detail back after a restart without depending on any separate database service.

**Browsing**

- **FR-013**: The main page MUST offer a clearly labelled way to reach the archive.
- **FR-014**: The archive MUST list every archived reel, ordered with the most recently created first.
- **FR-015**: Each listed reel MUST show its still image, source title, creation date and time, clip count, duration, and the settings it was made with.
- **FR-016**: The archive MUST state the total amount of storage occupied by all archived reels.
- **FR-017**: The archive MUST present an explicit empty state when nothing has been archived.
- **FR-018**: A single unreadable or incomplete entry MUST NOT prevent the remaining entries from being listed.

**Playing and downloading**

- **FR-019**: Users MUST be able to play any archived reel within the archive page.
- **FR-020**: Playback MUST support seeking to an arbitrary position rather than only sequential play.
- **FR-021**: Users MUST be able to download any archived reel under a name that identifies it.

**Deleting**

- **FR-022**: Users MUST be able to permanently delete any archived reel.
- **FR-023**: The system MUST require an explicit confirmation before deleting, and MUST leave the reel untouched if the confirmation is abandoned.
- **FR-024**: Deleting a reel MUST remove its video, its still image, its reference face image, and its recorded details from storage.
- **FR-025**: A deleted reel MUST NOT reappear in the archive, including after a restart.
- **FR-026**: The system MUST NOT delete any archived reel on its own initiative. Retention is unlimited and every deletion is user-initiated.

**Preserved behaviour**

- **FR-027**: The existing generation flow — submitting a video and a face image, watching progress, and seeing the finished reel — MUST continue to work unchanged.
- **FR-028**: The system MUST continue to process one video at a time and refuse concurrent submissions.

### Key Entities

- **Archived Reel**: One finished reel, kept permanently until the user deletes it. Holds the playable video, a still image representing it, the reference face image it was made from, and the details below. Identified in a way that stays stable across restarts and never collides with another entry, including two reels made from the same source video.
- **Reel Details**: The recorded facts about one archived reel — source title, source address, creation date and time, clip count, source duration, reel duration, resolution, reframed clip count, and the five settings the job ran with. Readable without any prior process being alive.
- **Archive**: The whole collection of archived reels, presented newest first, with a known total size on disk.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of successfully generated reels remain playable after an application restart. Today this figure is 0%.
- **SC-002**: A user who has generated reels in the past can find and start playing a specific past reel within 30 seconds of opening the app, without having saved anything locally.
- **SC-003**: Deleting a reel frees essentially all of the space it occupied, with no orphaned files left behind — verified by comparing the archive's reported size and actual disk use before and after.
- **SC-004**: No archived reel is ever removed except by an explicit user deletion — verified by confirming the count is non-decreasing across restarts and across further generations.
- **SC-005**: An archive holding 100 reels lists them without the page becoming unusable.
- **SC-006**: A single corrupted or partially deleted entry never prevents the other entries from being listed or played.
- **SC-007**: The existing generate-a-reel flow completes with no user-visible change other than the reel afterwards being present in the archive.

## Assumptions

- **Single user, trusted network.** The app has no concept of accounts and is reached on a home network. The archive is shared by anyone who can open the app; no per-user separation or access control is required.
- **Deletion is immediate and permanent.** There is no recycle bin, no undo, and no soft-delete. The confirmation step is the only safeguard, which is what "permanently delete" was taken to mean.
- **Unlimited retention was chosen deliberately** over automatic eviction, so a reel is never lost without the user asking. Showing the total size is the agreed compensating control against the disk filling silently.
- **Existing reels are not migrated.** Reels that exist when this feature ships are in job working directories that the next restart clears; the archive begins empty. Anything the user wants to keep must be downloaded before upgrading.
- **The still image is a frame taken from the reel itself**, not the uploaded face image, so the listing shows what the reel actually contains. The reference face image is kept as well, but as a recorded detail.
- **Storage is a normal writable directory** on a volume that outlives the application, already the case for the current deployment.
- **Scale is personal.** Hundreds of reels, not tens of thousands. Listing may load all entries without pagination.
- **Downloads keep today's naming scheme**, which already distinguishes reels made from the same source video at different times.
- **Archive growth is the user's responsibility**, informed by the displayed total size. The app does not monitor free disk space.
