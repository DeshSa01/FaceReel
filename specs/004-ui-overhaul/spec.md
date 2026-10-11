# Feature Specification: UI/UX Overhaul and Rebrand to Supercut

**Feature Branch**: `004-ui-overhaul`

**Created**: 2026-10-10

**Status**: Draft

**Input**: User description: "Overhaul and modernize the UI/UX of the app. The current UI is boring and unsophisticated. It has no logo or favicon, and the application needs a new name. Add dark mode support. Be imaginative about what's missing and add features/polish that make it sparkle and shine."

## Context

The application works well and looks like a form. Its three pages (sessions home,
session, archive) are plain cards of text on a grey background. Each carries its own copy
of the same styling, so they drift apart. It has no logo and no favicon. In a row of
browser tabs it is a blank page with the word "FaceReel".

Some interactions are also rougher than they need to be:

- The screenshot field only accepts a click and a file picker. It ignores drag-and-drop
  and paste, which is how a screenshot usually arrives.
- Starting work takes a "Create session" click and a page load before the user can paste
  a link.
- Progress is a sentence and a bar. Once the tab is in the background, nothing shows that
  anything is happening.
- A finished reel, the moment the whole app exists for, gets a heading and a video
  element.
- The archive is a grid with no search, sort or filter, and it uses a browser alert
  when a delete fails.

Dark mode exists only in a narrow sense: the pages follow the operating system's
setting, and the user can't override it. The dark palette is the light one inverted
rather than designed.

This feature gives the application a new name and identity, rebuilds the visual design
across every page, adds a light/dark/system theme choice, and adds a set of polish
features. Each one exists to make the moments that matter (starting, waiting, receiving
a reel, finding an old one) feel deliberate.

**What does not change**: how reels are made, how the queue is ordered, what a session
is, and what is stored. This is a presentation feature. Every capability that exists
today must still exist afterwards, reachable from the same page.

## Clarifications

### Session 2026-10-10

- Q: What is the application's new name? → A: **Supercut**. "A supercut" is the established term for a montage of every instance of one thing, which is exactly what the app produces. (Glimpse and Cameo were considered; Cameo collides with the Cameo celebrity-video service.)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The application has an identity (Priority: P1)

The user opens the application and sees a name, a logo, and a consistent header on
every page. In a crowded browser tab strip they find it by its favicon. On their phone
they add it to the home screen, and it gets a proper icon and opens like an app.

**Why this priority**: This is what the user asked for directly: a name, a logo, a
favicon. It is also what everything else hangs on. The visual redesign, the theme
control and the polish features all live inside the shell this story builds.

**Independent Test**: Open each of the three pages and confirm the same header, logo
and name appear on each. Open twelve other tabs and find the application by favicon
alone, in both a light and a dark browser theme. Add it to a phone's home screen and
confirm the icon and name.

**Acceptance Scenarios**:

1. **Given** any page of the application, **When** it loads, **Then** a shared header shows the logo and the application name, with navigation to Sessions and Archive and the current page visibly marked.
2. **Given** the application is open in a browser tab, **When** the user looks at the tab strip, **Then** the tab shows the application's favicon and a title naming both the page and the application (e.g. "Archive · Supercut").
3. **Given** the browser's own interface is in a dark theme, **When** the tab strip shows the favicon, **Then** the favicon is as legible as it is against a light tab strip.
4. **Given** the user adds the application to a phone or desktop home screen, **When** they open it from there, **Then** it shows the logo as its icon and the application name as its label, and opens without browser chrome wherever the browser allows that for the address it is served from (see FR-033a).
5. **Given** a reel is downloaded, **When** the user looks at the file name, **Then** any prefix that used to name the old brand uses the new one.

---

### User Story 2 - A modern, cohesive visual design (Priority: P1)

Every page is rebuilt on one shared design language: a type scale, a spacing rhythm, a
palette, components that look and behave the same everywhere (buttons, inputs, cards,
badges, toggles, sliders, menus), and motion that explains changes rather than
decorating them. Loading shows the shape of what is coming instead of a blank. An empty
state says what to do next, with an illustration rather than a sentence on a card.

**Why this priority**: This is the heart of "boring and unsophisticated". Without it,
a new name and logo sit on top of the same form.

**Independent Test**: Walk through the full existing flow on the new design: create
a session, add three videos, watch them process, receive the joined reel, open it in
the archive, delete a reel. Confirm every step uses the shared components and that
nothing which worked before is missing or behaves differently.

**Acceptance Scenarios**:

1. **Given** any two pages, **When** they are compared, **Then** equivalent elements (primary button, secondary button, text input, card, status badge) look and behave identically.
2. **Given** a page is waiting for its first data, **When** it renders, **Then** it shows a placeholder in the shape of the content to come (skeleton), not an empty area or a bare spinner.
3. **Given** a list with nothing in it (no sessions, empty queue, empty archive), **When** it is shown, **Then** it shows an illustrated empty state that names the next action and offers it as a button.
4. **Given** a video in the queue changes state (waiting → processing → done or failed), **When** the change arrives, **Then** the row transitions to its new state visibly, rather than being silently replaced, and its status is shown as a coloured badge with an icon, not colour alone.
5. **Given** the user has asked their operating system to reduce motion, **When** any page animates, **Then** the animation is replaced by an instant change or a simple fade.
6. **Given** an action fails (add video, retry, delete, remove, discard), **When** the failure is reported, **Then** it appears as a message tied to that action or as a dismissible toast, never as a browser alert or confirmation dialog.
7. **Given** a screen 360 pixels wide, **When** any page is used, **Then** nothing scrolls horizontally, every control can be tapped, and the pinned progress bar never covers the control the user needs.

---

### User Story 3 - Choose light, dark, or follow the system (Priority: P2)

The user switches the application between Light, Dark and System from a control in the
header. The choice sticks across reloads, pages and visits from that browser. In System
mode the application follows the operating system, including when the operating system
switches over at sunset. The dark theme is designed as its own palette, not the light
one inverted.

**Why this priority**: The user named dark mode explicitly. It ranks below identity and
the redesign only because a basic OS-following dark mode already exists. This story adds
the user's control over it and a dark theme designed in its own right.

**Independent Test**: With the OS in light mode, choose Dark. Reload, navigate to every
page, and close and reopen the browser; confirm Dark persists with no flash of light on
any load. Switch to System and toggle the OS appearance; confirm the application follows
within a second without reload.

**Acceptance Scenarios**:

1. **Given** the user has never chosen a theme, **When** they open the application, **Then** it follows the operating system's appearance.
2. **Given** the user chooses Light, Dark or System, **When** they reload or open another page, **Then** the same theme applies from the first frame, with no flash of the other theme.
3. **Given** System is selected, **When** the operating system's appearance changes, **Then** the application changes with it without a reload.
4. **Given** the application is open in two tabs, **When** the theme is changed in one, **Then** the other changes to match.
5. **Given** the dark theme, **When** reels, thumbnails, screenshots and the video player are shown, **Then** they sit on surfaces designed for media (no bright borders or halos around video), and status colours stay distinguishable from one another.
6. **Given** the browser refuses to remember preferences (private window, blocked storage), **When** the application loads, **Then** it follows the operating system and the theme control still works for the current page.

---

### User Story 4 - Getting a video in is effortless (Priority: P2)

The user copies a YouTube link and a screenshot, opens the application, and pastes
both. A pasted link shows the video's thumbnail and title before they submit, so they
know they have the right one. The screenshot appears as a round face chip labelled
"Looking for", so who the app is searching for is never in doubt. The user starts from
the home page itself: pasting a link there creates the session and carries the link
into it.

**Why this priority**: Adding videos is the most repeated action. It currently takes
the most clicks, and it ignores drag-and-drop and paste, which is how screenshots
usually travel.

**Independent Test**: From the home page with no session open, paste a YouTube link,
paste a screenshot from the clipboard, and submit. Confirm a session is created, the
video is queued, and the user did not use a file picker or a separate "create session"
step.

**Acceptance Scenarios**:

1. **Given** the home page, **When** the user pastes or types a YouTube link into its "start" field and confirms, **Then** a new session is created and opened with that link already in its add-video form.
2. **Given** the add-video form, **When** the user drags an image onto the screenshot area, or pastes an image anywhere on the page, **Then** that image becomes the screenshot, shown as a face chip.
3. **Given** the user drops or pastes something that is not an image, **When** it arrives, **Then** it is rejected with a message saying an image is needed, and the previous screenshot is kept.
4. **Given** a valid YouTube link has been entered, **When** the form recognises it, **Then** a preview shows that video's thumbnail and, where available, its title, before submission.
5. **Given** a link that is not a recognisable YouTube video link, **When** the user enters it, **Then** the field explains what is expected before the user submits, and the form still accepts any link the server accepts today.
6. **Given** each video in the queue, **When** the queue is shown, **Then** each row shows its video thumbnail and the face chip of the person it is looking for.
7. **Given** a session with a previous video, **When** the form is prefilled with that video's screenshot and settings (existing behaviour), **Then** the face chip shows the reused screenshot and says it is reused.
8. **Given** the clip fine-tuning controls, **When** the form is shown, **Then** they sit in a collapsed "Advanced" section that keeps the existing sliders, the "Use recommended" option, and the measured explanation of what the recommendation achieves. The section opens automatically when the values differ from the defaults.

---

### User Story 5 - Progress you can feel, and a reveal worth waiting for (Priority: P2)

While a video processes, the user sees where it is in the pipeline: a stage track
(download → scan → refine → frame → stitch) with the current stage animated and the
finished stages ticked. They also see the elapsed time. When they switch to another
tab, the browser tab's title and favicon still show the progress. When the session's
reel is ready, the application celebrates briefly and tastefully, presents the reel
large with its stats, and offers to download or share it. If the user allowed it, a
system notification tells them even when the browser is in the background.

**Why this priority**: Making a reel takes many minutes. The waiting and the
receiving are the experiences the user actually has, and today both are a sentence of
text.

**Independent Test**: Add a video and switch to another tab. Confirm the tab's title
and favicon show progress. Return and confirm the stage track matches the reported
stage. Let the session finish and confirm the celebration plays once, the reel is
presented, and a system notification arrived if permitted.

**Acceptance Scenarios**:

1. **Given** a video is processing, **When** its row or the pinned progress bar is shown, **Then** it shows the pipeline stages with the current one highlighted, completed ones marked, its percentage, and the time elapsed on this video.
2. **Given** any page is open in a background tab while work is processing, **When** the user looks at the tab, **Then** the tab title begins with the current percentage, and, in browsers that repaint changed favicons, the favicon shows a progress indicator.
3. **Given** nothing is processing, **When** the user looks at the tab, **Then** the title and favicon are the normal ones.
4. **Given** a session's joined reel becomes ready, **When** the user is on that session's page, **Then** a short celebration plays once, and the reel is presented prominently with its duration, clip count, resolution and the number of videos joined.
5. **Given** the user has seen a session's celebration, **When** they reload the page or open it again, **Then** the celebration does not replay. It is tied to the existing "acknowledged" notice, so it shows once per finished session.
6. **Given** the user has opted in to notifications, **When** a session's reel is ready or a session's join fails, **Then** a system notification names the session and opens it when clicked.
7. **Given** the user has not opted in, **When** they first add a video to a session, **Then** they are offered notifications once, in-page, with a clear "not now". Declining is remembered, and the application never asks the browser for permission without that click.
8. **Given** the queue is paused waiting for YouTube to be reachable (existing behaviour), **When** progress is shown, **Then** the stage track shows a distinct "waiting for network" state with the countdown, visually different from both progress and failure.
9. **Given** a finished reel, **When** the user chooses to share it, **Then** they can copy a direct link to the reel, or, where the device supports it, hand it to the device's share sheet.

---

### User Story 6 - An archive that's a pleasure to browse (Priority: P3)

The archive becomes a gallery. Thumbnails preview the reel when hovered or focused. The
user can search by title, filter to session reels or single reels, and sort by newest,
oldest, longest or largest. Opening a reel shows it in a viewer that moves to the next
or previous reel with the arrow keys and closes with Escape. A storage meter shows how
much space the archive uses, so the disk filling up stays a visible risk.

**Why this priority**: The archive grows without bound by design (nothing is deleted
automatically). Browsing it becomes a chore long before it becomes a problem. It is P3
because the core flow is complete without it.

**Independent Test**: With 30 or more reels archived, find a specific one by searching
part of its title, narrow it to session reels, and step through five reels in the viewer
using only the keyboard.

**Acceptance Scenarios**:

1. **Given** the archive, **When** the user types in its search field, **Then** the grid narrows as they type to reels whose title contains the text, ignoring case.
2. **Given** the archive, **When** the user selects a kind filter (All, Sessions, Single videos) or a sort order (Newest, Oldest, Longest, Largest), **Then** the grid updates immediately, and the choice is still applied on their next visit.
3. **Given** a reel card on a device with a pointer, **When** the pointer rests on it or it receives keyboard focus, **Then** a muted preview of the reel's first few seconds loops in place of the poster frame, and stops when the pointer or focus leaves.
4. **Given** the reel viewer is open, **When** the user presses the left or right arrow key, **Then** the previous or next reel in the current filtered, sorted order opens. Escape closes the viewer.
5. **Given** the archive, **When** it is shown, **Then** a storage meter displays the total size of all reels, and the number of reels.
6. **Given** the user deletes a reel, **When** they confirm the deletion (the existing confirmation naming the reel is kept), **Then** the card animates out, the meter updates, and a toast confirms what was deleted and how much space was freed.
7. **Given** a search or filter matching nothing, **When** the grid is empty, **Then** it says so and offers to clear the search or filter.

---

### User Story 7 - Jump between the clips inside a reel (Priority: P3)

When watching a reel, the user sees its clips laid out as a strip under the player,
each segment sized to its clip's length, with the current clip highlighted. "Next clip"
and "previous clip" controls skip between them. For a session reel, the strip also
shows which source video each stretch came from.

**Why this priority**: A reel is a sequence of moments, and today it plays as one
undifferentiated video. This turns it into something the user can navigate. It is
last because it is the only story that needs the application to keep information it
does not keep today.

**Independent Test**: Make a new reel with several clips, open it, and confirm the
number of clip-strip segments equals its clip count and that "next clip" lands at
the start of each segment in turn.

**Acceptance Scenarios**:

1. **Given** a reel made after this feature ships, **When** it plays, **Then** a clip strip under the player shows one segment per clip, sized to its length, and next/previous controls move between clips.
2. **Given** a session reel, **When** the user hovers or focuses a stretch of the clip strip, **Then** it names the source video that stretch came from.
3. **Given** a reel made before this feature shipped, **When** it plays, **Then** it plays as it does today, with no marks and no error.

---

### Edge Cases

- **Favicon on dark tab strips**: a mark designed only for a light background vanishes on a dark tab strip. The favicon must read on both (User Story 1, scenario 3).
- **Progress favicon in several tabs**: every open tab shows the same progress, since they all reflect the same single line of work. None of them competes or flickers.
- **Very long titles** (YouTube titles routinely exceed 100 characters): truncated with an ellipsis in rows and cards. The full title is available on hover and in the viewer, and the layout never breaks.
- **YouTube thumbnail unavailable** (video removed or private, or YouTube unreachable during the existing network-wait pause): a branded placeholder appears, never a broken image icon.
- **A full session (10 videos) on a phone**: the queue stays readable and the add-video form stays reachable without excessive scrolling.
- **Pasting an image while typing in the URL field**: the image becomes the screenshot and the URL text is untouched. Pasting text never replaces the screenshot.
- **Several images pasted or dropped at once**: the first is used, and the user is told only one screenshot is used per video.
- **Theme change mid-video**: changing theme while a reel plays does not interrupt playback.
- **Notification permission previously blocked in browser settings**: the in-page offer explains that notifications are blocked and how to re-enable them, rather than offering a button that does nothing.
- **Celebration while the user is elsewhere**: if the reel finishes while the user is on another page or tab, the celebration plays when they next open that session's page, once, and not at all if they already dismissed the bar's notice.
- **Session reel replaced by a retry** (existing behaviour): the new reel is a new finish and earns its own celebration and notification.
- **Archive filters remembered but the archive has changed**: a remembered filter that now matches nothing shows the "nothing matches" state with a way to clear it, not a blank page.
- **Reduced motion**: skeletons, celebrations, hover previews, card transitions and the stage track all respect the user's reduced-motion preference. Hover previews do not auto-play in that mode.
- **Served over plain HTTP on the home network**: notifications, the share sheet and one-click clipboard access are unavailable there, though they work on `localhost` during development. Copy-link falls back to a method that works on HTTP. The notification offer and share button are not shown (FR-033a).
- **Preferences cannot be stored**: theme, archive filters and the notification answer all fall back to their defaults without errors.

## Requirements *(mandatory)*

### Functional Requirements

**Identity and shell**

- **FR-001**: The application MUST be renamed, and the new name MUST replace "FaceReel" on every user-visible surface: page titles, headings, the header, the home-screen label, descriptive copy, and the prefix of downloaded session-reel file names. The new name is **Supercut**.
- **FR-002**: The application MUST have a logo with a full version (mark plus name) and a mark-only version. Both MUST be legible from 16×16 pixels up to 512×512 pixels, and on both light and dark backgrounds.
- **FR-003**: The logo concept MUST express the product: finding one person across footage and cutting it together. A suggested direction is a viewfinder or face-detection bracket combined with a film frame or cut mark. It MUST NOT use any third party's marks or likeness.
- **FR-004**: The application MUST provide a favicon, a high-resolution icon for home-screen and app-switcher use, and an install description, so that it can be added to a phone or desktop home screen with its own name, icon, theme colour and standalone window.
- **FR-005**: Every page MUST share one header containing the logo, the application name, navigation to Sessions and Archive with the current page marked, and the theme control.
- **FR-006**: Every page's browser tab title MUST name the page and the application, and the session page's title MUST identify the session (e.g. by its title or short id).

**Design system**

- **FR-007**: All pages MUST draw on one shared definition of colours, type scale, spacing, corner radii, shadows and motion timings. No page may keep its own private copy of these values.
- **FR-008**: The application MUST provide shared components used consistently on every page: primary, secondary, quiet and destructive buttons, text input, image drop zone, toggle, slider, card, status badge, toast, modal, empty state, skeleton placeholder and tooltip.
- **FR-009**: Status MUST be conveyed by colour and by an icon or text label together, never by colour alone.
- **FR-010**: Interactive elements MUST show a visible focus indicator for keyboard users, and every action MUST be reachable by keyboard.
- **FR-011**: Every animation MUST respect the user's reduced-motion preference by being removed or reduced to a simple fade.
- **FR-012**: Pages MUST be fully usable from 360 pixels wide upwards, with tap targets of at least 44×44 pixels on touch devices and no horizontal scrolling.
- **FR-013**: Errors from user actions MUST be shown next to the action that failed or as a dismissible toast. Browser alert, confirm and prompt dialogs MUST NOT be used anywhere.
- **FR-014**: Loading states MUST use skeleton placeholders shaped like the content they stand in for. Empty states MUST name and offer the next action.
- **FR-015**: Live updates (state changes, progress) MUST be announced to assistive technology without announcing every percentage tick; at most one announcement per stage change or state change.

**Theme**

- **FR-016**: Users MUST be able to choose Light, Dark or System from the header on any page. System MUST be the default.
- **FR-017**: The chosen theme MUST persist per browser across reloads, pages and visits, and MUST apply from the first rendered frame, with no visible flash of the other theme.
- **FR-018**: In System mode, the application MUST follow changes to the operating system's appearance without a reload.
- **FR-019**: A theme change in one tab MUST be reflected in the application's other open tabs in the same browser.
- **FR-020**: The dark theme MUST be designed as its own palette, with media surfaces suited to video and imagery. Both themes MUST meet WCAG 2.1 AA contrast: 4.5:1 for body text, and 3:1 for large text, icons and the boundaries of controls.

**Adding videos**

- **FR-021**: The home page MUST offer a "start" field into which a YouTube link can be pasted. Submitting it MUST create a new session and open it with that link carried into the add-video form. The existing explicit "create session" action MUST remain available.
- **FR-022**: The screenshot input MUST accept an image by click-to-choose (existing behaviour), by drag-and-drop onto the drop zone, and by pasting an image anywhere on the session page while the add-video form is visible.
- **FR-023**: Non-image input to the screenshot MUST be rejected with an explanation, keeping any screenshot already chosen. When several images arrive at once, the first MUST be used and the user told so.
- **FR-024**: The chosen screenshot MUST be shown as a face chip labelled as the person being looked for, including when it is a reused screenshot from the previous video.
- **FR-025**: On entry of a recognisable YouTube video link, the form MUST show that video's thumbnail and, where available, title, before submission. Recognition MUST NOT block submitting a link the server accepts today.
- **FR-026**: Each queue row MUST show the video's thumbnail and the face chip of its screenshot, with a branded placeholder when a thumbnail cannot be loaded.
- **FR-027**: The clip fine-tuning controls MUST move into a collapsible "Advanced" section that keeps every existing slider, the "Use recommended" option, the reset action, and the existing measured explanations verbatim in meaning. The section MUST open automatically when its values differ from the defaults.
- **FR-028**: The existing zoom and 4K toggles and the explanation of what their combination produces MUST be kept and given the new toggle component.

**Progress and completion**

- **FR-029**: A processing video MUST show a stage track of the pipeline's stages, with completed stages marked, the current stage highlighted, the percentage, and the elapsed time for that video. The track MUST appear in its queue row and, in condensed form, in the pinned progress bar.
- **FR-030**: The network-wait pause MUST have its own visual state, including the countdown, distinct from progress and from failure.
- **FR-031**: While work is processing, every open page of the application MUST prefix its tab title with the current percentage. In browsers that repaint a changed favicon, it MUST also show progress in the favicon; Safari does not reliably do so, and there the title alone carries it. Both MUST return to normal when nothing is processing.
- **FR-032**: When a session's joined reel becomes ready, that session's page MUST present the reel prominently with its stats and download and share actions, and play a short celebration once per finished reel. "Once" is governed by the same acknowledgement that already stops the progress bar's notice repeating.
- **FR-033a**: Notifications, the native share sheet, one-click clipboard copy and full app installation are features browsers only grant to secure origins. The deployment is served over plain HTTP on the home network, which is not one, though `localhost` during development is. Each of these MUST be offered only where the browser actually allows it, and MUST degrade without errors elsewhere. Copy-link MUST still work by a fallback. The notification offer MUST NOT appear where notifications cannot work, and the tab title and favicon remain the background signal there.
- **FR-033**: Users MUST be able to opt in to system notifications through an in-page offer made once, when they first add a video to a session. Declining MUST be remembered. The application MUST NOT request notification permission except in direct response to the user accepting that offer.
- **FR-034**: When opted in, a system notification MUST be shown when a session's joined reel is ready or its join fails, naming the session and opening it when clicked.
- **FR-035**: A finished reel MUST offer "copy link" and, where the device supports a native share sheet, "share".

**Archive**

- **FR-036**: The archive MUST offer search by title (case-insensitive substring, narrowing as the user types), a kind filter (All, Sessions, Single videos), and sorting (Newest, Oldest, Longest, Largest). Filter and sort choices MUST persist per browser.
- **FR-037**: On devices with a pointer, a reel card MUST loop a muted preview of the reel's first 6 seconds while hovered or focused, and stop when it is not. Previews MUST NOT auto-play under reduced motion.
- **FR-038**: The reel viewer MUST support next and previous reel with arrow keys and on-screen controls, following the archive's current filter and sort, and MUST close with Escape.
- **FR-039**: The archive MUST show a storage meter with the total size and number of reels.
- **FR-040**: The existing delete confirmation naming the reel MUST be kept, restyled as an in-page confirmation. After deletion, the card MUST animate out, and a toast MUST state what was deleted and the space freed.

**Clip navigation**

- **FR-041**: For reels made after this feature ships, the application MUST record where each clip begins in the finished reel and, for session reels, which source video each clip came from.
- **FR-042**: The reel player (session page and archive viewer) MUST show the reel's clips as a strip beneath the player, with segments sized to each clip and the current one highlighted, offer next and previous clip controls, and for session reels name the source video of the stretch under the pointer or focus.
- **FR-043**: Reels without recorded clip information MUST play exactly as they do today, without marks and without error.

**Parity and constraints**

- **FR-044**: Every existing capability MUST remain available after the overhaul, on the same page as today. The capabilities are: listing and joining running sessions; creating a session; copying a session id; adding, removing and queueing videos; the 10-video limit message; screenshot and settings prefill; zoom and 4K toggles; fine-tuning; the "will finish after current" warning; cross-session wait explanations; network-wait countdown; per-video results and failures, including the full failure detail on hover; retrying failed videos from both the session page and the archive; discarding an empty session; the joining progress; the finished, nothing-to-join and join-failed outcomes; the pinned progress bar on every page, with its dismissible notices; archive browsing, playback, download, delete and the "from session" link.
- **FR-045**: Existing refresh rates for visible pages MUST be unchanged (session page every second, sessions list every two seconds). A hidden tab MAY check the shared progress no more often than once every 10 seconds, solely to keep its tab title, favicon and notifications current, which FR-031 and FR-034 cannot do otherwise. Visual polish MUST NOT add work to the server's processing of videos. The one exception is recording the clip map (FR-041), which is allowed only once its cost has been measured on the deployment host and found negligible against stitching.
- **FR-046**: The README MUST be updated in the same change to use the new name and describe any behaviour this feature changes, such as starting a session from the home page.

### Key Entities

- **Theme preference**: the user's choice of Light, Dark or System. One per browser, not per session or server-wide. Defaults to System.
- **Archive view preference**: the user's last search-independent archive choices (kind filter, sort order). One per browser.
- **Notification preference**: whether the user accepted, declined or has not yet been asked about system notifications. One per browser.
- **Brand assets**: the logo (full and mark-only), favicon, home-screen icons and install description. Static, and shipped with the application.
- **Clip map** (new, per reel): the ordered start time of each clip within a finished reel and, for session reels, the source video each clip came from. Stored alongside the reel's existing archived information. Absent for reels made before this feature.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In a browser window with 12 or more tabs open, the user picks out the application's tab by favicon alone in under 2 seconds, with the browser in both light and dark appearance.
- **SC-002**: 100% of text and control boundaries on every page, in both themes, meet the WCAG 2.1 AA contrast ratios in FR-020.
- **SC-003**: Across 20 reloads and navigations in each theme, a frame-by-frame screen recording shows zero frames of the other theme.
- **SC-004**: From the home page, with a link and a screenshot already on the clipboard, a user queues their first video in 3 actions or fewer (paste link and confirm, paste image, submit), down from 6 today, and in under 15 seconds.
- **SC-005**: Every capability listed in FR-044 passes a walkthrough on the new design. Zero regressions.
- **SC-006**: Every page is fully usable at 360 pixels wide with no horizontal scrolling, verified on one real phone.
- **SC-007**: On the home network, each page shows meaningful content (skeleton or data) within 1 second of navigation, and is no slower to become usable than today.
- **SC-008**: With the application in a background tab, the user can tell the current percentage of work from the tab alone, at most about 10 seconds out of date. If notifications are available and enabled, the user learns that a session reel is ready within 15 seconds of it finishing, or within about a minute when the tab has been hidden long enough for the browser to slow its background timers.
- **SC-009**: In an archive of 50 or more reels, a user finds a named reel in under 10 seconds using search or filter.
- **SC-010**: The owner, shown the old and new versions of each of the three pages side by side, prefers the new version on all three and would describe it as a finished product rather than a tool.
- **SC-011**: The celebration plays exactly once per finished reel per browser, across reloads and tabs, verified by finishing three sessions.

## Assumptions

- **Single user on a trusted network** (constitution scope). Theme, archive view and notification preferences are per browser, not per account, since there are no accounts.
- **Rebranding stops at user-visible surfaces.** The container image name, the host storage path, environment variables, and internal identifiers stay as they are. Renaming them would break the existing deployment and offers the user nothing. The planning phase may revisit this, but must then document the migration in the README.
- **Thumbnails come from YouTube's public thumbnail images**, loaded by the browser. This is the one external request this feature adds. The application already depends on reaching YouTube, and the edge cases cover what happens when it can't.
- **No new heavyweight dependencies** (constitution Principle IV). The redesign is expected to be achievable without adopting a front-end framework or build step. Any dependency the plan proposes must be justified there.
- **Hover previews play the archived reel itself**, muted and from its start. Generating separate preview clips would add encoding work to a host where encoding is already the bottleneck.
- **Clip maps can be recorded at stitch time**, because the pipeline already knows each clip's interval when it cuts. This adds information to the archive and does not change how reels are made.
- **Celebration means brief and restrained**: a short burst of motion and a presentation of the reel, under about two seconds, and never sound.
- **Elapsed time, not an estimate of time remaining.** The application has no measurement on which to base a remaining-time estimate (constitution Principle II), so this feature shows only elapsed time.
- **The home page's "start" field and the explicit create button coexist**, so the familiar path stays available.

## Out of Scope

- Changes to detection, clip selection, encoding or queue ordering.
- Accounts, sharing reels outside the home network, or public links.
- Renaming the container image, repository or storage locations (see Assumptions).
- Editing reels (trimming, reordering, removing clips) in the browser. Clip navigation is for watching only.
- Localisation into other languages.
