---

description: "Task list for 004 UI/UX Overhaul and Rebrand to Supercut"
---

# Tasks: UI/UX Overhaul and Rebrand to Supercut

**Input**: Design documents from `/specs/004-ui-overhaul/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: There are no automated test tasks. The spec doesn't request them, and the constitution doesn't mandate a test framework. Verification is the environment-tagged [quickstart.md](./quickstart.md) plus [`contrast.py`](./contrast.py). Each story ends with the quickstart section that proves it.

**Organization**: Tasks are grouped by user story, so each story can be implemented, verified and deployed on its own (plan "Delivery order").

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel: a different file, with no dependency on an incomplete task.
- **[Story]**: US1–US7, from spec.md.
- Paths are relative to the repo root. The layout is flat: Python modules at the root, pages and assets under `static/`.

## Conventions that apply to every task

- **Comments (constitution I)**: every chosen constant gets a comment saying it is *chosen, not measured* and why, citing the research decision (e.g. `# research D10`). Ordering hazards get a comment too.
- **No new runtime dependencies (IV)**: no packages, CDNs or web fonts.
- **Colours**: only tokens from [contracts/design-tokens.md](./contracts/design-tokens.md), never literals outside the token block.
- **Motion**: only inside `@media (prefers-reduced-motion: no-preference)` (research D15).
- **Dialogs**: never `alert`, `confirm` or `prompt` (FR-013).
- **Python changes need an app restart** to verify. Pages and static files reload live.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Directories, the tooling, and the static-serving route everything else loads through.

- [X] T001 Create the asset directories `static/css/`, `static/js/`, `static/brand/` and `tools/`. Each gets its real file in later tasks; add no placeholder files.
- [X] T002 Replace the `progress_js()` route in `app.py` with `GET /static/{path:path}`, per [contracts/http.md](./contracts/http.md) "GET /static/{path}" and research D14.
  - In `lifespan()`, alongside the other start-up work, fill a module-level dict `STATIC_FILES` (empty at import) mapping each allowed relative path to its absolute path. It holds every file under `static/css`, `static/js` and `static/brand`, plus `progress.js`, `icons.svg` and `manifest.webmanifest`.
  - The handler looks `path` up in the dict and 404s if it's missing. It never joins `path` onto the filesystem.
  - Serve with `FileResponse`, the media type mapped from the extension (`.webmanifest` → `application/manifest+json`), and `Cache-Control: no-cache`.
  - Move the existing staleness comment from `progress_js()` onto the new route. Comment that the allow-list is validate-not-sanitise (Principle V).
  - Comment why it is filled in `lifespan()`: the comment above `store` promises that module scope touches no disk.
  - Note: files added later need an app restart to be served. Say so in the comment.
- [X] T003 [P] Create `tools/render-icons.sh` (executable, `set -euo pipefail`). It renders each SVG in `static/brand/` to its PNG sizes with headless Chrome:
  - Use `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu --hide-scrollbars --default-background-color=00000000 --window-size=N,N --screenshot=<out> <svg>`.
  - Outputs, all in `static/brand/`:
    - `favicon-32.png` from `mark-small.svg`
    - `icon-192.png` and `icon-512.png` from `mark.svg`, with transparent corners
    - `apple-touch-icon.png` (180) and `icon-maskable-512.png` from `mark-maskable.svg`, **opaque** (no `--default-background-color` override). iOS applies its own corner mask and fills any transparency with black, so a pre-rounded transparent tile shows black corners.
  - The header comment says why Chrome is used (no SVG rasteriser installed, and a Python one would be a runtime dependency; research D6), that it is run by hand when the logo changes, and that the PNGs are committed.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The design system and shared script every story builds on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 Create `static/css/supercut.css`, section 1, **tokens**: every token in [contracts/design-tokens.md](./contracts/design-tokens.md).
  - Colours as `light-dark(<light>, <dark>)`, with `:root { color-scheme: light dark; }` and `:root[data-theme="light"] { color-scheme: light; }` / `:root[data-theme="dark"] { color-scheme: dark; }` (research D2).
  - The dark shadows switch to hairline rings.
  - `--tap-min` under `@media (pointer: coarse)`.
  - Head the block with a comment pointing at `specs/004-ui-overhaul/contrast.py` and saying it must be re-run after any colour change (Principle II).
- [X] T005 `static/css/supercut.css`, section 2, **base**:
  - Box-sizing reset; `body` using `--bg`, `--text`, `--font` and `--lh-body`.
  - The type scale on `h1`–`h3`, with `--tracking-tight` at `--fs-xl` and up.
  - Links in `--accent-text`.
  - `:focus-visible` as a 2px `--focus` ring, offset 2px (FR-010).
  - The `.skip-link`, the `.visually-hidden` utility, and `.tabular` for `tabular-nums`.
  - `[hidden]{display:none!important}`.
  - The `@view-transition { navigation: auto; }` rule and `.app-header { view-transition-name: header; }`, both inside the reduced-motion guard (research D16).
- [X] T006 `static/css/supercut.css`, section 3, **components**: every class in [contracts/ui-shell.md](./contracts/ui-shell.md) §6, using tokens only.
  - **Required behaviours**:
    - `.btn` variants all meet `--tap-min`.
    - `.btn-primary` is solid `--accent` with `--on-accent`, never the gradient (research D3).
    - `.toggle` styles `input[type=checkbox][role=switch]`.
    - `.slider` styles the range track with `--control` and the thumb with `--accent`.
    - `.badge` fills are `color-mix(in oklab, var(--status) 12%/18%, var(--surface))` with full-colour text, and every badge has an icon slot.
    - `.skeleton` uses a shimmer, animated only under the motion guard.
    - `.toast-stack` is fixed bottom-right (bottom-centre under 600px), stacked above the progress bar using a `--bar-height` custom property that `progress.js` sets.
    - `dialog.modal` styles `::backdrop`.
    - `.empty` is a centred illustration, title, body and action.
    - `.thumb` is a 16:9 frame on `--media`, and `.is-placeholder` shows the mark at 30% opacity.
  - **Defer**: leave `.stage-track`, `.clip-strip`, `.reel-presenter` and `.face-chip` as empty commented section headers for US4, US5 and US7 to fill.
- [X] T007 [P] Create `static/icons.svg`, a `<svg>` holding `<symbol id="i-…" viewBox="0 0 24 24">` for each icon the contracts use:
  - link, image, upload, clipboard, copy, share, download, play, pause, chevron-left, chevron-right
  - x, check, clock, loader, alert-triangle, wifi-off, minus
  - sun, moon, monitor, search, sliders, trash, refresh, bell, sparkles, film, scissors, user, external-link
  - Use stroke-based 2px paths with `stroke="currentColor"`. Paths may be adapted from Lucide (ISC); if they are, put the ISC licence text in an XML comment at the top of the file (Principle IV: vendored asset, licence recorded).
- [X] T008 Create `static/js/shell.js` as an IIFE exporting `window.Supercut`, with the **core** members from [contracts/ui-shell.md](./contracts/ui-shell.md) §3:
  - `icon`, `toast`, `announce` (creates the single `aria-live="polite"` region on load), `badge`, and `copyText`.
  - `copyText` tries the clipboard API first, then a hidden-textarea `execCommand` fallback; it never throws (research D9).
  - `fmtDuration`, `fmtBytes` and `fmtDate`, moved verbatim from the current pages' helpers.
  - `el(tag, cls, text)`, the same helper the pages use today.
  - Leave clearly marked sections for `theme`, `notify`, `celebrate`, `celebrated`, `youtubeId`, `youtubeThumb`, `thumbImg`, `faceChip` and `stageTrack`, which later stories add.
  - Comment that `shell.js` must load before `progress.js` (ui-shell §1).

**Checkpoint**: The stylesheet, sprite and shell can be loaded by any page, and stories can begin.

---

## Phase 3: User Story 1 — The application has an identity (Priority: P1) 🎯 MVP

**Goal**: Supercut has a name, logo, favicon, home-screen icons and a shared header on every page (FR-001 to FR-006).

**Independent Test**: [quickstart.md](./quickstart.md) §2.

- [X] T009 [P] [US1] Draw the "cut frame" mark per research D5. Create in `static/brand/`:
  - **`mark.svg`** (viewBox `0 0 64 64`): a 22%-radius rounded-square tile filled with a 135° `linearGradient` from `#5B3DF5` to `#E5306F`. On it, in white:
    - four corner brackets (stroke 5, round caps)
    - a centred play triangle split by a diagonal gap of about 3 units, with the halves offset about 1.5 units along the gap
  - **`mark-small.svg`**: the same tile, with stroke-7 brackets, an enlarged triangle and **no** gap.
  - **`favicon.svg`**: a copy of `mark-small.svg`.
  - **`mark-maskable.svg`**: the tile extended to full bleed, with the glyph scaled into the central 80% safe zone.
  - **`logo.svg`**: `mark.svg` beside the wordmark "Supercut" as `<text>`, with `font-family` set to the `--font` stack, weight 800, and tracking −0.02em. "cut" is filled with the gradient.
  - Check every file reads at 16px and 512px on both white and `#0A0A10` before moving on.
- [X] T010 [US1] Run `tools/render-icons.sh` to produce and commit the PNGs: `favicon-32.png`, `apple-touch-icon.png`, `icon-192.png`, `icon-512.png` and `icon-maskable-512.png`. Open each one to confirm nothing is cropped, that `favicon-32`, `icon-192` and `icon-512` have transparent corners, and that `apple-touch-icon` and `icon-maskable-512` are opaque full-bleed squares.
- [X] T011 [P] [US1] Create `static/manifest.webmanifest`, exactly as the normative JSON in [contracts/http.md](./contracts/http.md) "GET /manifest.webmanifest".
- [X] T012 [US1] In `app.py`, add `GET /favicon.ico` (serves `static/brand/favicon-32.png` as `image/png`) and `GET /manifest.webmanifest` (serves the manifest as `application/manifest+json`), both `Cache-Control: no-cache`. Comment that browsers request `/favicon.ico` regardless of `<link>` tags. Also change `FastAPI(title="FaceReel")` to `"Supercut"`.
- [X] T013 [P] [US1] In `static/css/supercut.css`, add `.app-header` styles:
  - a sticky top bar on `--surface`, with a `--border` bottom hairline and `backdrop-filter: saturate(1.4) blur(12px)` over a 85%-opacity surface
  - the brand link: the 28px mark plus the wordmark at `--fw-black`, with "cut" in `background: var(--gradient); background-clip: text; color: transparent`
  - nav links with `aria-current="page"` marked by a 2px `--accent` underline
  - a right-aligned slot (`.app-header-actions`) for the theme control added in US3
  - collapse under 600px: the wordmark stays and the nav becomes icon plus short label
- [X] T014 [US1] Rewrite the `<head>` and add the header in `static/index.html`. Use the page skeleton from [contracts/ui-shell.md](./contracts/ui-shell.md) §1 and §2, **without** the theme script, which comes in US3:
  - `<title>Sessions · Supercut</title>`, the description meta, the icon/manifest/theme-color/Apple metas, and the stylesheet link.
  - `body[data-page="sessions"]`, the skip link, the header with Sessions marked current, and `<main id="main">`.
  - Script order: `shell.js`, then `progress.js`.
  - Keep the existing page markup and script working inside `<main>` for now. US2 restyles it.
  - Replace the "FaceReel" heading and copy with "Supercut".
- [X] T015 [US1] Do the same for `static/session.html`, with Sessions marked current (a session belongs to Sessions). The base title is `"<session title or 'New session'> · Supercut"`, set by the page script once the snapshot loads, with "Session · Supercut" until then (FR-006). Change the download attribute from `facereel-session-${sid}.mp4` to `supercut-session-${sid}.mp4`.
- [X] T016 [US1] Do the same for `static/archive.html`, with Archive marked current and the title "Archive · Supercut". Replace the "FaceReel Archive" heading.
- [X] T017 [US1] In `archive.py`'s `archive_session()`, change `filename` to `f"supercut-session-{sid}.mp4"`. Comment that existing sidecars are deliberately not rewritten, because a sidecar is a record of what was made (research D17).
- [X] T018 [US1] In `static/progress.js`, rename the brand-bearing identifiers: element id `facereel-progress` → `supercut-progress`, and `window.FaceReelProgress` → `window.SupercutProgress`. Leave `FaceReelProgress` as a deprecated alias for one release, with a comment. Leave the `ACK_KEY` value alone; US5 migrates it. Update the header comment to name the tokens it now relies on.
- [X] T019 [US1] Amend `.specify/memory/constitution.md`: retitle it "Supercut Constitution" and update the scope sentence's app name. Bump the version to 1.0.1 (PATCH: a name change with no change of meaning) and set Last Amended to the date of the change. Prepend a Sync Impact Report recording 1.0.0 → 1.0.1 and the rename. This ships with US1 because that is where the rename lands (constitution, Development Workflow).
- [X] T020 [US1] Docs for US1, in the same change (constitution: documentation must not outlive its truth). `README.md`:
  - retitle it "Supercut", noting once that it was formerly FaceReel
  - new session reels download as `supercut-session-<id>.mp4`; older ones keep their names
  - `tools/render-icons.sh`, and when to run it
  - the browser floor (research D2: Safari 17.5, Chrome 123, Firefox 120; older browsers get the light theme)
  - adding to the home screen, and that over plain HTTP Android opens it in a browser tab (research D6)
  - leave the image, compose and storage-path names alone, because they are real
  `HANDOFF.md`: change the title and the prose naming the app, keeping repository, registry and path names.
- [ ] T021 [US1] Verify US1 with quickstart §2, steps 1–4 on [local] and 5–6 on [phone]/[deploy]. Fix anything that fails before moving on.

**Checkpoint**: The new identity is live on every page. The app still works exactly as before.

---

## Phase 4: User Story 2 — A modern, cohesive visual design (Priority: P1)

**Goal**: Every page is rebuilt on the shared components, with skeletons, empty states, badges, transitions, toasts, accessible live updates and a 360px-safe layout. There are no behaviour regressions (FR-007 to FR-015, FR-044).

**Independent Test**: [quickstart.md](./quickstart.md) §1 and §8, plus the spec's US2 independent test, walked through on the new design.

- [X] T022 [US2] Restyle `static/progress.js`'s injected `STYLE`. Use the design tokens with no literal fallbacks other than the old ones kept as a last resort. Use the shared `.btn-quiet .btn-sm` for Dismiss, and set `document.documentElement.style.setProperty("--bar-height", …)` wherever it already sets `body.style.paddingBottom`, so toasts stack above it. Keep every behaviour: polling, stale marking, notices, links.
- [X] T023 [US2] Rebuild `static/index.html`'s `<main>` on components, keeping all current behaviour:
  - the hero section: an `<h1>` "Every moment they appear. One reel." and one explanatory line (adapted from the current `.sub` copy)
  - the **existing** "Create session" button as `.btn-primary` (the start field comes in US4)
  - "Running sessions" as `.card`s, each with the title, a `.badge` per count from `countsLine` (processing, waiting, done, failed, joining), the started time, the id in `--font-mono`, and **Join** as `.btn-secondary`
  - three `.skeleton-row` placeholders until the first poll returns (FR-014)
  - with no sessions, the running section stays hidden and the hero is the empty state
  - create errors via `Supercut.toast(..., {kind: "error"})`
  - keep the 2 s poll and the visibility logic untouched (FR-045)
  - delete the page's `<style>` block, keeping only page-layout rules that are not components (if any) in a short `<style>` with no colour literals
- [X] T024 [US2] Rebuild `static/session.html`'s `<main>` on components, keeping all current behaviour and element ids where the page script uses them:
  - **Header row**: the session title, the short id with a copy `.btn-icon` (now using `Supercut.copyText`, then a toast), and the "N of 10 videos" line.
  - **Layout**: two columns at ≥ 960px (composer left, queue right), stacked below that.
  - **Form**: `.field`/`.input` for the URL, the existing click-to-choose `.dropzone`, `.toggle` switches for zoom and 4K (`role="switch"`), the outcome line as a quiet `.card`, and the tuning `<details>` restyled with `.slider`s. Keep every label, hint and measured explanation **verbatim**.
  - **Queue**: rows render through `Supercut.badge(state, label)` with the data-model §7 icons and labels.
  - **Transitions**: when a row's state changes between polls, add a `.is-changed` class for `--t-med`, so the badge pops (motion-guarded). To do this, keep a `Map` of id → last state and patch rows in place rather than rebuilding `innerHTML`.
  - **Join and ended cards**: restyled as `.card`. The joining bar gets a gradient fill. The `.notice` warning gets the warning tint.
  - **"Session not found"**: an `.empty` state with a link home.
  - **Errors**: form errors stay inline; remove, discard and retry failures go to toasts.
  - **Skeleton**: until the first snapshot, show a skeleton composer and queue.
  - Keep the 1 s poll and the visibility logic untouched.
  - Delete the page-level component CSS.
- [X] T025 [US2] Rebuild `static/archive.html`'s `<main>` on components, keeping current behaviour (search, filter and preview come in US6):
  - **Grid**: a `.card-media .card-interactive` grid, with the poster in `.thumb`, the Session badge, the Unavailable badge, and title, meta and size.
  - **Total**: the existing total line, kept as text for now (the meter comes in US6).
  - **Loading**: skeleton thumbs until `/api/archive` returns.
  - **Empty archive**: an `.empty` state with a "Go to Sessions" action.
  - **Viewer**: becomes `<dialog class="modal modal-viewer">` opened with `showModal()`, which gives Escape and focus trapping. The backdrop click closes it. Keep the `#<id>` hash opening it.
  - **Delete confirmation**: `<dialog class="modal modal-confirm">` naming the reel.
  - **Delete failures**: replace `alert("Delete failed.")` with `Supercut.toast("Couldn't delete …", {kind:"error"})` (FR-013).
  - **Viewer contents**: the joined and not-included lists as restyled lists with check and x icons. Retry, Download, From-session and Delete as `.btn` variants.
- [X] T026 [P] [US2] Create the illustrated empty states as small inline SVGs (≤ 2 KB each, `currentColor` plus gradient accents) in `static/brand/empty-sessions.svg`, `static/brand/empty-archive.svg` and `static/brand/empty-search.svg`. Reference them from the `.empty` illustration slot in T023, T024 and T025.
- [X] T027 [US2] Wire `Supercut.announce()` into the session page script (`static/session.html`) for each video's state transitions ("Video 2 is processing", "Video 2 done: 14 clips", "Video 3 failed: <reason>") and for the session's ended states. Never announce on percentage changes (FR-015).
- [X] T028 [US2] Responsive pass across `static/css/supercut.css` and the three pages at 360px:
  - no horizontal scroll (FR-012); long titles truncate with an ellipsis and keep the full title in `title=`
  - the form's submit stays clear of the progress bar, because `--bar-height` is reserved on `body`
  - touch targets ≥ 44px under `pointer: coarse`
  - Check in a 360px-wide responsive viewport.
- [X] T029 [US2] Docs for US2: grep `README.md` and `HANDOFF.md` for descriptions of page behaviour this story changed (the archive's delete confirmation and failure handling, the session page layout, and the HANDOFF notes on page markup and `alert`). Correct each one in the same change.
- [ ] T030 [US2] Verify US2: run quickstart §1 (contrast and literal checks), §8.2 (keyboard-only), §8.3 (VoiceOver) and §8.6 (no `alert`, `confirm` or `prompt`). Walk the US2 independent test on [local]. Fix any regressions against the FR-044 capability list.

**Checkpoint**: The whole app looks new and nothing it did before is missing. This is the P1 MVP; deploy it.

---

## Phase 5: User Story 3 — Choose light, dark, or follow the system (Priority: P2)

**Goal**: A Light/Dark/System control that persists, never flashes, follows the OS live and syncs across tabs (FR-016 to FR-020).

**Independent Test**: [quickstart.md](./quickstart.md) §3.

- [X] T031 [US3] Add the inline theme script from [contracts/ui-shell.md](./contracts/ui-shell.md) §1 to the `<head>` of `static/index.html`, `static/session.html` and `static/archive.html`, **before** the stylesheet `<link>`. Each copy gets a comment naming the other two files and saying why it is inline and first (research D2, FR-017).
- [X] T032 [US3] In `static/js/shell.js`, implement `Supercut.theme`:
  - `get()` reads `localStorage["supercut.theme"]` (inside `try`), defaulting to `"system"`.
  - `set(mode)` writes it (removing the key for `"system"`), sets or removes `document.documentElement.dataset.theme`, and refreshes the control.
  - A `window` `storage` listener applies changes made in other tabs (FR-019).
  - System mode needs no `matchMedia` listener, because CSS `color-scheme` follows the OS. Comment this so nobody adds one.
- [X] T033 [US3] Add the theme control to the `.app-header-actions` slot of all three pages (`static/index.html`, `static/session.html`, `static/archive.html`):
  - A `.btn-icon` showing the current mode's icon (sun, moon or monitor), with `popovertarget` pointing at a `popover` menu.
  - The menu has three `role="menuitemradio"` items with `aria-checked`.
  - `shell.js` binds it on load.
  - Style the popover menu in `static/css/supercut.css`.
- [X] T034 [US3] Dark-media pass in `static/css/supercut.css`:
  - `video`, `.thumb`, the viewer and the presenter sit on `--media` with no light border (US3 scenario 5).
  - Check each status badge in dark is distinguishable from the others.
  - Re-run `python3 specs/004-ui-overhaul/contrast.py`.
- [X] T035 [US3] Docs for US3: describe the Light/Dark/System control in `README.md`, including that the choice is per browser.
- [X] T036 [US3] Verify US3 with quickstart §3, steps 1–5, on [local], including the frame-stepped screen recording for SC-003.

**Checkpoint**: The theme is under the user's control on every page.

---

## Phase 6: User Story 4 — Getting a video in is effortless (Priority: P2)

**Goal**: Start from the home page with a link; paste or drop the screenshot; see YouTube previews, face chips and queue thumbnails; tuning under "Advanced" (FR-021 to FR-028).

**Independent Test**: [quickstart.md](./quickstart.md) §4.

- [X] T037 [P] [US4] Create `youtube.py` (stdlib only), per research D7 and [contracts/http.md](./contracts/http.md) "GET /api/youtube/preview":
  - `video_id(url) -> str | None` recognises `watch?v=`, `youtu.be/`, `/shorts/`, `/live/` and `/embed/` on `youtube.com`, `www.`, `m.` and `music.` hosts, and youtu.be. It returns the id only if it matches `^[A-Za-z0-9_-]{11}$`.
  - `preview(vid) -> dict`:
    - builds the oEmbed URL itself from the validated id
    - fetches it with `urllib.request.urlopen(..., timeout=4)`
    - returns `{id, title, author, thumbnail}` with `title`/`author` set to `None` on any exception or non-200
  - **Cache**: a module-level `OrderedDict` LRU of 256 entries, guarded by a `threading.Lock`. Failures expire after 60 s.
  - **Comments**: the 4 s timeout, 256 entries and 60 s failure TTL are all chosen, not measured. The cache is per process, which is fine under the single-instance constraint. The user's URL is never fetched (SSRF, Principle V).
- [X] T038 [US4] In `app.py`, add `GET /api/youtube/preview` taking a `url` query parameter. Return `400` "Not a YouTube video link." when `youtube.video_id` returns `None`, otherwise `youtube.preview(id)`. It must be a plain `def`, so FastAPI runs the blocking fetch in its threadpool. Comment that this keeps the event loop free.
- [X] T039 [P] [US4] In `sessions.py`'s `_summary()`, add `video_urls`: the URLs of the first 4 non-removed videos, in order (data-model §4).
- [X] T040 [US4] In `static/js/shell.js`, implement:
  - `youtubeId(url)`, the same rules as `youtube.video_id`, and a pure function
  - `youtubeThumb(id)`
  - `thumbImg(url, alt)`: an `<img loading="lazy" decoding="async">` in a `.thumb`; on `error` or with no id it swaps to `.thumb.is-placeholder` (FR-026)
  - `faceChip(src, label)`
  - In `static/css/supercut.css`, fill the `.face-chip` section: a 40px round crop with a 2px gradient ring, and the label beside it. `.is-reused` gets a muted label.
- [X] T041 [US4] Home start field in `static/index.html`. Above the create button, add a `<form>` holding an `.input-lg` with a link icon (placeholder "Paste a YouTube link to start", `type="url"`, `inputmode="url"`, `autofocus`) and a **Start** `.btn-primary`. Demote "Create session" to a `.btn-quiet` "or start an empty session". On submit:
  1. Do a light shape check (`new URL()` succeeds), with an inline error otherwise.
  2. Call `POST /api/sessions`.
  3. Navigate to `/session/<id>?url=<encodeURIComponent(link)>` (research D8, FR-021).
  - Running-session cards gain a thumbnail strip of up to 4 `Supercut.thumbImg` from `video_urls`.
- [X] T042 [US4] Link hand-off and URL preview in `static/session.html`:
  - On load, read `?url`, put it into `#url`, call `history.replaceState` to drop the parameter, and focus the dropzone (research D8). Comment why each step is there.
  - Under the URL field, add a preview card. On `input` (debounced 400 ms, chosen) with a recognised `Supercut.youtubeId`:
    - show `thumbImg` immediately
    - fetch `/api/youtube/preview` and show the title when it arrives
  - With an unrecognised non-empty link, show the inline hint "That doesn't look like a YouTube video link." without blocking submit (FR-025).
- [X] T043 [US4] Paste and drop for the screenshot in `static/session.html` (FR-022, FR-023):
  - `dragenter`/`dragover`/`dragleave`/`drop` on `#drop`, toggling `.is-dragover`.
  - A `document` `paste` listener, active while `#form-card` is visible, that takes the first `image/*` item from `clipboardData.items`.
  - Non-image input calls `Supercut.toast("Screenshots must be an image.", {kind:"error"})` and keeps the current file.
  - With several images, use the first and toast "Only one screenshot is used per video; using the first."
  - **Pasting text never touches the screenshot.** Pasting an image while the caret is in `#url` must not change the field's text: call `preventDefault()` only when an image was taken.
  - **Getting the file into the form**: a picked file sets `useOwnFile = true` and is stored in a variable `chosenFile`. Use `DataTransfer` to assign it to `#file.files` where supported, otherwise keep `chosenFile` and change the submit handler to read `chosenFile ?? $("file").files[0]`.
- [X] T044 [US4] Show the screenshot as a face chip in `static/session.html`: replace the dropzone's `<img id="preview">` presentation with `Supercut.faceChip(src, "Looking for")` once a file is chosen, and `"Same as video N"` with `.is-reused` when prefilled (FR-024). The dropzone collapses to a compact "Change" affordance once filled.
- [X] T045 [US4] Queue rows in `static/session.html` gain a leading `Supercut.thumbImg(v.url)` and a `faceChip` of `/api/sessions/<sid>/videos/<vid>/screenshot` (FR-026). The row layout is a 16:9 thumb (96px wide), the body, and the badge, collapsing to a 64px thumb at 360px.
- [X] T046 [US4] In `static/session.html`, wrap the existing tuning `<details>` as an "Advanced" disclosure with a sliders icon. Remove the `open` attribute. In `setKnobs()` and `renderPrefill()`, set `details.open = true` whenever any slider differs from `knobs` defaults (FR-027). Keep "Use recommended", "Reset to defaults" and every hint's text verbatim, and restyle the zoom and 4K switches as `.toggle` with the outcome line beneath (FR-028).
- [X] T047 [US4] Docs for US4. `README.md`: starting a session by pasting a link on the home page; pasting or dropping the screenshot; the link preview, and that thumbnails load from YouTube. `HANDOFF.md`: `youtube.py`, the preview route, and its rule that the server never fetches the user's URL (research D7).
- [ ] T048 [US4] Restart the app, then verify US4 with quickstart §4: steps 1–3 and 5–6 on [local], and step 4 (the oEmbed route from the container) on [deploy].

**Checkpoint**: Queuing a video takes a paste, a paste and a click.

---

## Phase 7: User Story 5 — Progress you can feel, and a reveal worth waiting for (Priority: P2)

**Goal**: Stage track and elapsed time; tab title and favicon progress; a once-per-completion celebration and presenter; capability-gated notifications, copy and share; the network-wait state (FR-029 to FR-035, FR-033a).

**Independent Test**: [quickstart.md](./quickstart.md) §5.

- [X] T049 [US5] In `sessions.py`'s `pick_next()`, add `"started": time.monotonic()` to the `_runtime` entry for both the join branch and the video branch (data-model §2, research D11). Comment that it is in-memory on purpose: a restarted video starts over, so its timer should too.
- [X] T050 [US5] Expose `elapsed_s` in `sessions.py`, as `int(time.monotonic() - started)` when `started` is present. Add it to:
  - `_public_video()` for processing videos
  - `snapshot()`'s `join` object
  - `active()`'s video and join `processing` payloads (not the network-wait payload)
  - Strip the raw `started` key from every response so monotonic floats never leave the process.
  - Also add `"completed_at": s["completed_at"]` to `active()`'s terminal payload (data-model §3).
  - Add `"zoom": bool(v["tuning"].get("zoom"))` to `active()`'s video payloads, including network wait, so the bar's compact stage track knows whether to show "frame" ([contracts/http.md](./contracts/http.md)).
- [X] T051 [US5] In `static/js/shell.js`, implement `stageTrack({stage, progress, elapsed_s, zoom, network})` per data-model §7:
  - The stages are download, scan, refine, an optional frame stage, and stitch, using the pipeline-stage mapping table.
  - Done stages get a check icon, the current one an animated ring, and network the `.is-paused` style with a wifi-off icon.
  - Show `NN%` and an elapsed clock in `tabular-nums`, ticking locally every second and re-synced by `update()`.
  - Return an element with an `update(args)` method.
  - Fill the `.stage-track` section in `static/css/supercut.css`, including a compact `.stage-track.is-compact` for the bar. The ring animation goes under the motion guard.
- [X] T052 [US5] Use the stage track in `static/session.html`'s processing rows (pass `zoom: v.tuning.zoom`) and in its joining card (a single "Joining reels" stage). Give the network-wait waiting row the `.is-paused` track with the countdown text (FR-029, FR-030). Rows update in place through `update()`, not by being rebuilt.
- [X] T053 [US5] Rework `static/progress.js`:
  - **Bar**: render the compact stage track via `Supercut.stageTrack`, passing `zoom: job.zoom`.
  - **Announcements (FR-015)**: call `Supercut.announce()` when the job's stage or status changes (e.g. "Session 4f2a91, video 2 of 5: scanning", "Session reel ready"). Never announce on percentage changes. Skip this on the page of the job's own session, where the session page's own announcements (the US2 task) already cover it.
  - **Hidden polling**: poll every 10 s while hidden instead of stopping (research D10). Update the visibility comment to explain the reversal of 002 D2 and the browser throttling caveat.
  - **New members**: add `completionKey(job)` and `isAcknowledged(key)` to `window.SupercutProgress`, and switch acknowledgement to `localStorage["supercut.acknowledged"]` holding the completion key (research D12).
  - **One-time migration**: if `facereel.acknowledged` exists, then on the first terminal payload whose `id` equals it, write that payload's completion key as acknowledged, then remove the old key.
  - **Comment**: the previous session-id key is why retry-rebuilt reels never re-announced. This change fixes it.
- [X] T054 [US5] Tab title and favicon progress in `static/js/shell.js` (FR-031):
  - On `DOMContentLoaded`, record `baseTitle`.
  - Wrap `document.title` changes by pages through a `Supercut.setTitle(base)` helper. Update the three pages to call it instead of assigning `document.title`.
  - Subscribe to `SupercutProgress`:
    - while processing, set `"NN% · <Stage> · " + baseTitle`
    - otherwise restore `baseTitle`
  - **Favicon**:
    - draw a 64×64 canvas: the `favicon-32.png` image scaled up, plus a 4px progress arc in the gradient
    - set it as the `<link rel="icon">` href with `toDataURL()`
    - redraw only when the integer percentage or the stage changes
    - restore the original hrefs when idle
  - Comment that Safari may not repaint dynamic favicons, and that the title is the primary signal.
- [X] T055 [US5] Implement the `Supercut.notify` members in `static/js/shell.js`, per ui-shell §3 and research D9:
  - `available()` requires `isSecureContext`.
  - `offer(container)` renders an inline `.card` with a bell icon and the text "Get a notification when your reel is ready?", with **Turn on** and **Not now** buttons.
    - **Turn on** calls `Notification.requestPermission()` inside the click handler and stores `"accepted"` or `"declined"`.
    - With state `"blocked"`, it renders a one-line explainer of how to re-enable notifications in browser settings.
    - With state `"unavailable"`, it renders nothing.
  - **Firing**: subscribe to `SupercutProgress`. On a transition into a terminal payload whose completion key hasn't been notified this page-life, when state is `"accepted"` and `document.hidden`, fire `new Notification("Supercut", {body, icon: "/static/brand/icon-192.png", tag: key})`. Its `onclick` focuses the window and navigates to `/session/<sid>` (FR-034).
  - **Deduplication**: the `tag` deduplicates across tabs.
- [X] T056 [US5] In `static/session.html`, call `Supercut.notify.offer()` into a slot above the composer the first time the session has at least one video. Only call it once per browser, because the state machine handles the "already answered" cases (FR-033).
- [X] T057 [US5] Implement `Supercut.celebrate(targetEl)` and `Supercut.celebrated` in `static/js/shell.js` (research D12):
  - **Celebrate**: a full-viewport `<canvas>` overlay (`pointer-events:none`) with about 36 particles in the gradient colours, simple gravity, removed after ≤ 1600 ms. Add `.is-entering` to `targetEl` for the 400 ms spring-scale entrance.
  - **Reduced motion**: only a fade.
  - **Celebrated**: `has` and `add` over `localStorage["supercut.celebrated"]`, a JSON array capped at 50 with the oldest dropped. Comment that the 50 cap is chosen.
- [X] T058 [US5] Finished-reel presenter in `static/session.html` (FR-032, FR-035):
  - Restructure `#ended-card` for `finished` into `.reel-presenter`. Fill that section in `static/css/supercut.css` with a gradient 1px frame and `--glow`. It holds:
    - the video
    - stat chips: duration (`fmtDuration`), clips, resolution, videos joined
    - **Download** `.btn-primary`
    - **Copy link** `.btn-secondary`, copying `location.origin + "/archive#" + sid` through `Supercut.copyText`, then a toast
    - **Share** `.btn-secondary`, only when `Supercut.canShare(url)`
    - the retry button when some videos failed
    - "Start a new session" `.btn-quiet`
  - **Celebration**: on render of `finished`, compute the completion key `sid + "@" + s.completed_at`. If it is not in `celebrated` and not `SupercutProgress.isAcknowledged(key)`, call `celebrate(presenter)` and then `celebrated.add(key)`.
- [X] T059 [US5] Implement `Supercut.canShare(url)` and `Supercut.share({title, url})` in `static/js/shell.js`. Use `navigator.share` only when it exists and `navigator.canShare?.({url}) !== false`. Swallow `AbortError` (FR-035, FR-033a).
- [X] T060 [US5] "Now processing" card on `static/index.html`. Subscribe to `SupercutProgress`. While a job is processing, show a `.card` with:
  - the session label, "video N of M"
  - a thumbnail (via the session's `video_urls` from the sessions poll, matched by `session_id` and `index`)
  - a full-size `stageTrack`, and an "Open session" link
  - Hide it when idle. No new polling.
- [X] T061 [US5] Docs for US5. `README.md`: tab-title and favicon progress; that hidden tabs check every 10 s; that notifications, share and one-click copy need HTTPS or `localhost`, and that putting the app behind HTTPS would enable them (research D9). `HANDOFF.md`: the hidden-poll reversal of 002 D2, the completion-key fix, and the secure-context finding.
- [ ] T062 [US5] Restart the app and verify US5 with quickstart §5: steps 1 and 4–6 and 8 on [local]; steps 2, 3 and 7 on [deploy]. Confirm in particular that no notification offer appears and nothing errors over plain HTTP.

**Checkpoint**: Waiting is visible from anywhere, and the reel's arrival is an event.

---

## Phase 8: User Story 6 — An archive that's a pleasure to browse (Priority: P3)

**Goal**: Search, filter and sort with persistence; hover and focus previews; keyboard viewer navigation; storage meter; animated delete with a toast (FR-036 to FR-040).

**Independent Test**: [quickstart.md](./quickstart.md) §6.

- [X] T063 [US6] Toolbar in `static/archive.html`:
  - **Search**: a `.input` with a search icon and a clear `.btn-icon`. Filter on `input` with a case-insensitive substring match on `title`.
  - **Kind filter**: segmented buttons All · Sessions · Single videos (`aria-pressed`). `kind === "session"` maps to Sessions; everything else is Single videos.
  - **Sort**: a popover menu with Newest, Oldest, Longest (`output_duration`) and Largest (`size_bytes`).
  - **Persistence**: kind and sort persist to `localStorage["supercut.archive"]`, read inside `try`, with unknown values falling back to the defaults (data-model §5). Search is not persisted.
  - **Rendering**: one `view()` function derives the filtered, sorted list from `entries`. Both the grid and the viewer's previous/next use it.
- [X] T064 [US6] In `app.py`'s `list_archive()`, add `disk_total_bytes` and `disk_free_bytes` from `shutil.disk_usage(archive.ARCHIVE_DIR)` ([contracts/http.md](./contracts/http.md)). Comment that the archive is on the bind-mounted volume, so these are the host drive's real figures, and that the README's reason for showing the total is exactly this risk.
- [X] T065 [US6] Storage meter in `static/archive.html` and `static/css/supercut.css` (`.meter`): "N reels · X GB · Y GB free", with a slim bar showing the archive's share of the drive (`total_bytes / disk_total_bytes`) and the rest of the used space as a lighter segment. When free space drops under 10% (chosen), the bar and label take the warning colour. Replaces the plain total line (FR-039).
- [X] T066 [US6] "Recent reels" on `static/index.html` ([contracts/ui-shell.md](./contracts/ui-shell.md) §7, Sessions item 4): fetch `/api/archive` **once** on load (not polled; FR-045) and show the 6 newest entries as small `.card-media` cards linking to `/archive#<id>`, with a "View all →" link. Skeleton cards while loading. Hide the section when the archive is empty or the fetch fails.
- [X] T067 [US6] Hover and focus previews in `static/archive.html` (FR-037). On `pointerenter`/`focusin` of a card, when `matchMedia("(hover: hover)")` matches, reduced motion is off, and the entry is `available`:
  - after a 250 ms timer (chosen: sweeping the pointer across the grid shouldn't start fetches), insert `<video muted playsinline preload="auto" src="/api/archive/<id>/video">` over the poster and play it
  - loop only the first 6 s: on `timeupdate`, when `currentTime >= 6`, set `currentTime = 0` (chosen: long enough to recognise the reel, and it bounds the bytes fetched per hover; spec FR-037)
  - on `pointerleave`/`focusout`, clear the timer, pause the video, remove its `src` and remove the element, so the connection is released
  - Comment that previews play the reel itself rather than a generated clip (spec assumption: no added encoding).
- [X] T068 [US6] Viewer navigation in `static/archive.html` (FR-038):
  - previous and next `.btn-icon` arrows in the viewer dialog
  - a `keydown` handler on the dialog: ←/→ step through `view()` order, wrapping off. Escape is native to `<dialog>`.
  - update `location.hash` on each step, so the URL is shareable
  - add a matching `view-transition-name` on the opened card's thumb and the viewer video for the grow effect (research D16, motion-guarded)
- [X] T069 [US6] Delete flow in `static/archive.html` (FR-040). After a confirmed delete succeeds:
  - add `.is-leaving` to the card (fade and collapse over `--t-med`) and remove it on `transitionend`, or immediately under reduced motion
  - update the meter
  - `Supercut.toast("Deleted “<title>” · freed <fmtBytes(freed_bytes)>", {kind:"success"})`
  - The viewer closes, or advances to the next reel if there is one.
- [X] T070 [US6] Empty-result state in `static/archive.html`: when `view()` is empty but `entries` isn't, show `.empty` "Nothing matches" with a **Clear filters** action that resets search and kind (US6 scenario 7, and the remembered-filter edge case).
- [X] T071 [US6] Docs for US6: the `README.md` archive section gains search, filter, sort, hover previews, keyboard navigation and the disk-space meter. Keep the existing statements that deletion is permanent and that nothing is deleted automatically.
- [X] T072 [US6] Verify US6 with quickstart §6, steps 1–6, on [local], with 30 or more reels.

**Checkpoint**: The archive scales to hundreds of reels.

---

## Phase 9: User Story 7 — Jump between the clips inside a reel (Priority: P3)

**Goal**: Record a clip map at stitch and join time; render a clip strip with previous and next under every reel player; old reels unaffected (FR-041 to FR-043).

**Independent Test**: [quickstart.md](./quickstart.md) §7.

- [X] T073 [US7] In `pipeline.py`, add `_probe_duration(path) -> float` (`ffprobe -v error -show_entries format=duration -of csv=p=0`).
  - **Probe each segment**: in `cut_and_stitch()`, after each segment is cut and before the segments are deleted, probe it.
  - **Build clips**: a running total gives `clips = [{start, end, source_start}]`, 2 dp, with `source_start` being the interval's `start`.
  - **Return** `(output, clips)`.
  - **Docstring**: explain why it probes instead of summing `end - start`. The concat demuxer offsets by container duration, and frame rounding plus AAC priming make a nominal sum drift (research D13).
  - **Comment placeholder**: `MEASURED: <probe cost for a ~50-clip reel on the nucbox, from T082>`.
- [X] T074 [US7] In `pipeline.py`'s `process_job()`, unpack `output, clips = cut_and_stitch(...)` and add `"clips"` to the result. Before returning, check that `abs(clips[-1]["end"] - _probe_duration(output)) <= 0.05`. On a mismatch, set `clips = None` and log a warning, so wrong marks are never written (data-model §1 rules). Comment the 0.05 s tolerance as chosen: half a typical frame interval at 30fps rounded up, below what a viewer could notice.
- [X] T075 [US7] In `pipeline.py`'s `join_reels()`, compute `offsets`: the running total of the probed durations of the files actually concatenated. On the copy path, these are the `probes[i]["duration"]` already collected. On the normalise path, probe each `norm_*.mp4` before concatenation. Return `offsets` in the result dict. Comment why the normalised files are re-probed.
- [X] T076 [P] [US7] In `archive.py`, write `"clips": result.get("clips")` into `archive_job()`'s sidecar, and `info.get("clips")` into `archive_session()`'s, omitting the key when the value is `None`. Then extract `read_public_entry(reel_id) -> dict | None` from the loop body of `list_entries()`: the listing-shaped dict, with `size_bytes`, `has_thumb`, `has_screenshot`, `available` and friendly `videos[].reason`. Make `list_entries()` call it per directory, so the two shapes can't drift ([contracts/http.md](./contracts/http.md)).
- [X] T077 [US7] In `runner.py`'s `_run_join()`, build the session clip map (data-model §1):
  - Keep each joined video's `entry` and display index alongside `inputs`.
  - After `join_reels`, for each joined video `i` with offset `o`:
    - if `entry.get("clips")`, emit each clip shifted by `o`, tagged with `video`, `index` and `title`
    - otherwise emit one `{start: o, end: next_offset_or_output_duration, video, index, title, whole: True}`
  - Pass the result as `info["clips"]` to `archive.archive_session`.
  - Write the offsetting as a module-level pure function `session_clips(joined, offsets, total)`, so it is testable later (research D18).
- [X] T078 [US7] In `app.py`, add `GET /api/archive/{reel_id:path}`, returning `archive.read_public_entry` or 404. Declare it **after** the `/video`, `/thumb` and `/screenshot` routes, with a comment explaining that `:path` would otherwise swallow them.
- [X] T079 [P] [US7] Create `static/js/player.js` exporting `window.SupercutPlayer.attach(videoEl, entry)`, per [contracts/ui-shell.md](./contracts/ui-shell.md) §5:
  - **No clips**: when `entry.clips` is not a non-empty array, return `{destroy(){}}` and insert nothing.
  - **Strip**: otherwise insert a `.clip-strip` after `videoEl`, made of `<button class="clip-seg">` elements:
    - widths `flex-grow: end - start`, with `min-width: 3px`
    - session reels tinted by `(index - 1) % 6` and a divider at each video change
    - each button's accessible name per the contract
    - a hover or focus tooltip with the source title on session reels
  - **Controls**: previous and next `.btn-icon` buttons.
  - **Current clip**: `timeupdate` sets `.is-current`. Clicking sets `currentTime = start`.
  - **Keys**: `[` and `]` while focus is within the player or strip.
  - `destroy()` removes everything and its listeners.
  - Fill the `.clip-strip` section in `static/css/supercut.css`.
- [X] T080 [US7] Attach the player in both pages:
  - **`static/session.html`**: once `finished`, fetch `/api/archive/<sid>` once per completion key and call `SupercutPlayer.attach($("player"), entry)`. Destroy it when a retry reopens the session.
  - **`static/archive.html`**: on viewer open, call `attach` with the already-loaded entry, and `destroy` on close or step.
  - Add `<script src="/static/js/player.js">` to both pages.
- [X] T081 [US7] Docs for US7. `README.md`: clip navigation, and that only reels made from now on have it. `HANDOFF.md`: the `clips` sidecar field, why segment durations are probed (research D13), and the measured cost from the verify task below.
- [ ] T082 [US7] Restart the app, then verify US7 with quickstart §7, steps 1–3 and 5. **Step 4 (constitution II, owed)**: on the nucbox, time the probe loop for a reel of about 50 clips (wrap it with `time.monotonic()` logging, temporarily or permanently). Replace the `MEASURED:` placeholder in `pipeline.py`'s `cut_and_stitch` comment with the figure. If the cost is not negligible against stitch time, switch to nominal sums with a documented drift, and record why. While on the nucbox, also time a session join and fill the `MEASURED:` placeholder that feature 003 left in `join_reels`'s docstring, which this story edits.

**Checkpoint**: Every reel made from now on can be navigated clip by clip.

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Documentation truth, the constitution amendment, performance and full validation.

- [ ] T083 [P] Final docs consistency pass: each story already corrected its own docs. Read `README.md` top to bottom against the shipped app and fix any statement that is no longer true.
- [X] T084 [P] Add to `HANDOFF.md` a short "004 UI overhaul" section listing the new modules and files (`youtube.py`, `static/css`, `static/js`, `static/brand`, `tools/render-icons.sh`), the hidden-poll reversal, the completion-key fix and the secure-context finding.
- [X] T085 Performance budget check: measure the uncompressed sizes of `static/css/supercut.css` (≤ 40 KB), `static/js/shell.js` plus `static/js/player.js` (≤ 40 KB) and `static/icons.svg` (≤ 15 KB) (plan "Performance Goals"). Trim if any is over. Then run quickstart §8.5 on [deploy] for SC-007.
- [X] T086 Remove the deprecated `window.FaceReelProgress` alias from `static/progress.js` (T018) once all three pages use `SupercutProgress`. Grep `static/` for `FaceReel` and `facereel` and confirm the only remaining hits are the one-time `facereel.acknowledged` migration in `progress.js`.
- [ ] T087 Full validation on [deploy] and [phone]:
  - run every quickstart section end to end
  - do the FR-044 parity walk-through (§8.1, SC-005)
  - the 360px phone pass (§8.4, SC-006)
  - the owner side-by-side preference check (SC-010) against the previous image tag
  - Record any step that could not be run, by name, in the PR description (constitution: report honestly).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none. T002 needs an app restart before later assets are served.
- **Foundational (Phase 2)**: depends on Setup. **Blocks all stories.**
- **US1 (Phase 3)**: depends on Foundational.
- **US2 (Phase 4)**: depends on US1 (it restyles the pages US1 gave a shell). Together they are the P1 MVP.
- **US3 to US7 (Phases 5–9)**: each depends on US1 and US2 being done, and otherwise only on Foundational. Two cross-story notes:
  - US5's T060 uses `video_urls` from US4's T039. If US5 ships first, move T039 into it.
  - US7's T080 attaches to the session presenter from US5's T058. If US7 ships first, attach to the existing `#player` instead.
- **Polish (Phase 10)**: after the stories you intend to ship. Each story carries its own docs task, so this phase is only a consistency pass.

### Within each story

Python changes first (they need a restart), then `shell.js` members, then page wiring, then the story's verification task.

Tasks on the same file are sequential. The three HTML pages are separate files, so per-page tasks with the same shape could run in parallel, but they're listed in order because each also edits shared CSS.

### Parallel Opportunities

- **Setup**: T003 alongside T002.
- **Foundational**: T007 (the sprite) alongside T004–T006 (CSS) and T008 (shell).
- **US1**: T009 (brand SVGs), T011 (manifest) and T013 (header CSS) together; then T010 after T009.
- **US2**: T026 (empty-state SVGs) alongside T023–T025.
- **US4**: T037 (`youtube.py`) and T039 (`sessions.py`) together, then T038. The front-end work proceeds while they're built.
- **US7**: T076 (`archive.py`) and T079 (`player.js`) alongside the `pipeline.py` work in T073–T075.
- **Polish**: T083 and T084 together.

---

## Parallel Example: User Story 7

```bash
# Server-side, independent files:
Task: "T073–T075 clip map in pipeline.py (cut_and_stitch probe, process_job, join_reels offsets)"
Task: "T076 sidecar clips + read_public_entry in archive.py"

# Client-side, independent of the server work:
Task: "T079 SupercutPlayer.attach in static/js/player.js"

# Then, sequentially: T077 runner.py → T078 app.py route → T080 page wiring → T082 verify + measure
```

## Parallel Example: User Story 4

```bash
Task: "T037 youtube.py id parsing + oEmbed + LRU"
Task: "T039 video_urls in sessions.py _summary()"
Task: "T040 youtubeId/thumbImg/faceChip in static/js/shell.js"
# then T038 (app.py route) → T041–T046 (pages) → T048 verify
```

---

## Implementation Strategy

### MVP first (P1: US1 + US2)

1. Phase 1 Setup, then Phase 2 Foundational.
2. Phase 3 (US1): name, logo, favicon, header. **Validate** with quickstart §2.
3. Phase 4 (US2): every page on the design system with full parity. **Validate** with quickstart §1 and §8.
4. **Deploy**, with the README, HANDOFF and constitution already updated by US1 and US2. This is the answer to "boring, unsophisticated, no logo, no name".

### Incremental delivery

5. US3, theme control. This is small, and dark already works by OS from the foundation. Deploy.
6. US4, effortless adding. Deploy.
7. US5, progress and reveal. Deploy, and run the [deploy]-only steps here especially.
8. US6, archive gallery. Deploy.
9. US7, the clip map. This is the only pipeline change, and it owes the probe-cost measurement. Deploy.
10. Polish: docs consistency pass, budget and full validation.

Each step is a coherent commit, or a few, deployed through the normal push-to-`main` image build. Every `sha-` tag is a rollback point.

---

## Notes

- A `[P]` marker means a different file with no dependency on incomplete work. Most page tasks share an HTML file and so are sequential.
- Commit messages carry the why (constitution, Development Workflow). In particular, call out the hidden-poll reversal (T053) and the completion-key bug fix (T053).
- Stop at any checkpoint to validate the story on its own.
