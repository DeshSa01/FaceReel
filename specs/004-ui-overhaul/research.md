# Research: UI/UX Overhaul and Rebrand to Supercut

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Date**: 2026-10-10

Each decision records what was chosen, why, and what was rejected. Values that are
chosen rather than measured say so (constitution Principle II). Presentation sizes and
timings have no measurement that could justify them, and the archive's thumbnail
constants already set that precedent.

---

## D1. No framework and no build step. One shared stylesheet and a few plain scripts.

**Decision**: The three pages stay hand-written HTML files served by FastAPI. Everything
they share moves into new static files:

- `static/css/supercut.css`: tokens, base styles and every component.
- `static/js/shell.js`: theme, toasts, the screen-reader announcer, tab title and favicon
  progress, notifications, copy and share, and YouTube link parsing.
- `static/js/player.js`: the clip strip (D13).
- `static/progress.js`: the existing bar, restyled.

Pages keep their own page-specific script inline, as today.

**Rationale**:

- The current pages are 150–600 lines each, and the repetition is CSS, not logic.
- A framework would add a toolchain, a lockfile and a build stage to a Docker image that
  today copies files and runs (Principle IV).
- Everything the redesign needs is in the browser platform as of 2026:
  - `light-dark()` and `color-scheme` (D2)
  - `<dialog>` for modals and the delete confirmation
  - the Popover API for the theme and sort menus
  - cross-document View Transitions (D16)
  - container queries and `:has()`

**Alternatives rejected**:

- *A component framework (React, Svelte, Lit)*: rejected for the build step and dependency
  closure, against three pages.
- *Tailwind*: needs a build to stay small. Its CDN build is a runtime fetch from a third
  party, which would break the app whenever that site is unreachable.
- *Keeping per-page CSS*: this is the drift FR-007 forbids.

---

## D2. Theme: `light-dark()` tokens, a `data-theme` override, and a four-line inline head script

**Decision**:

- Each colour token is declared once, as `--x: light-dark(<light>, <dark>)`.
- `:root { color-scheme: light dark }` makes System the default.
- `:root[data-theme="light"]` and `:root[data-theme="dark"]` pin `color-scheme`.
- Each page's `<head>` carries the same inline script, before the stylesheet link. It
  reads `localStorage["supercut.theme"]` inside `try` and sets `data-theme` on `<html>`.
- `shell.js` handles the rest:
  - It wires the header control.
  - It writes the preference.
  - It listens for `storage` events, so other tabs follow (FR-019).
- System mode needs no JavaScript to follow the OS (FR-018), because `color-scheme`
  resolves live.

**Rationale**:

- The flash of the wrong theme (FR-017, SC-003) can only be prevented by code that runs
  before first paint. An external script would block render for a network round trip.
  Inline blocks for no time.
- `light-dark()` halves the token file and cannot drift: there is no second block of dark
  values to forget.
- `color-scheme` also themes what CSS can't reach: scrollbars, native `<video>` controls,
  `<select>`, autofill and range tracks. Without it, those stay light on a dark page.

**Duplication accepted**: the head script is repeated in three files. It is four lines,
and making it external would reintroduce the flash. A comment in each copy names the
other two.

**Browser floor**: `light-dark()` needs Safari 17.5, Chrome 123 or Firefox 120 (all 2024).
This is a single-user app, and the owner's devices are current. Older browsers get the
light theme and keep working. That is acceptable, and the README records it.

**Alternatives rejected**:

- *Two token blocks under `prefers-color-scheme` plus `[data-theme]`*: needs the dark
  values written twice, once for "system and OS is dark" and once for "forced dark".
- *Server-side theme cookie*: would need a server round trip to change theme, and the
  server would carry state that only one browser cares about.

---

## D3. Palette: measured contrast, with coral kept for decoration only

**Decision**: the tokens and ratios in
[contracts/design-tokens.md](./contracts/design-tokens.md). The brand pairs an
electric violet (`#5B3DF5`) with a hot coral (`#E5306F`) as a 135° gradient. The gradient
appears in exactly four places:

- the logo tile
- progress fills
- the celebration
- the finished-reel presenter's frame

Coral is never used for text, and never behind white text in the dark theme.

**Measured** (WCAG 2.1 relative luminance, computed by
[`contrast.py`](./contrast.py), kept beside this file so it can be re-run when a token
changes):

| Pair | Light | Dark | Needed |
|---|---|---|---|
| Body text on page background | 16.81 | 16.80 | 4.5 |
| Muted text on raised surface (worst case) | 6.02 | 6.90 | 4.5 |
| Link/accent text on raised surface | 5.34 | 6.89 | 4.5 |
| Success / warning / danger text on raised | 5.12 / 5.12 / 4.86 | 9.08 / 8.35 / 6.21 | 4.5 |
| Status text on its own badge tint (narrowest) | 4.70 (danger) | 5.30 (danger) | 4.5 |
| Placeholder (`--muted`) on input (`--raised`) | 6.02 | 6.90 | 4.5 |
| White on primary button fill | 6.12 | 5.07 | 4.5 |
| Control boundary on page background | 3.12 | 3.89 | 3.0 |
| Primary fill against surface (dark) | n/a | 3.64 | 3.0 |
| Coral as text on surface | **4.21 (fails)** | 6.33 | 4.5 |
| White on coral | 4.21 | **2.91 (fails)** | 4.5 |

The first dark primary fill tried was `#7C63FF`. White on it measured **4.13 and
failed**. Darker steps measured `#6247F7` at 5.58 and `#6A50FA` at 5.07. `#6A50FA` was
chosen because it still separates from the dark surface at 3.64 and keeps the violet
reading as bright.

Light `--success` started as `#0B7A54`. It passed on surfaces, but measured **4.54** on its own 12% badge tint, too thin a margin, so it is now `#0A7350` (4.94 on its tint). The badge tints are measured directly rather than assumed from the `--raised` result.

Coral fails as text in light and behind white in dark, so the gradient never carries text.
That is why the primary button is solid violet, not gradient.

Decorative hairlines (`border`, 1.29:1 on light) are allowed below 3:1 only where they
are not the only thing identifying a control (WCAG 1.4.11). Inputs, toggles and slider
tracks use the `control` token, which passes.

**Alternatives rejected**:

- *Keep indigo `#4f46e5`*: passes contrast but is the default palette of half the web.
  It is part of what the user called "boring".
- *Gradient primary buttons*: fail contrast at the coral end (above).

---

## D4. Typography: system font stack, no web font

**Decision**: `system-ui, -apple-system, "Segoe UI", Roboto, sans-serif` for text and
`ui-monospace, "SF Mono", Menlo, monospace` for ids. Sophistication comes from the type
system, not the typeface:

- a modular scale (1.250, base 16px)
- tight tracking (−0.02em) on display sizes
- weights 450, 600 and 750
- `font-variant-numeric: tabular-nums` on every changing number (percentages, timers,
  sizes)

The wordmark in the header is live text in the same stack at weight 800. "cut" carries
the brand gradient through `background-clip: text`.

**Rationale**: On the owner's Apple devices the stack resolves to SF Pro, which is better
than any font we could ship. It costs no bytes, no licence, no network fetch, and no
font-loading layout shift on a page that polls every second.

**Alternatives rejected**:

- *Self-hosted Inter variable font*: about 100 KB subset per page load, plus a flash of
  unstyled text, to look like SF Pro on the devices that already have SF Pro.
- *Outlined wordmark paths*: would need a font editor in the toolchain to change one
  letter.

---

## D5. Logo: the "cut frame" mark

**Decision**: The mark is a rounded-square tile (22% corner radius) filled with the brand
gradient. It carries a white glyph:

- **Four corner brackets**, the face-detection box every camera draws around a face.
- **A play triangle** inside them.
- **A diagonal cut** through the triangle: a 1-unit gap, with the two halves offset half a
  unit along it.

Together these read as *found it* and *cut it*.

Three files, as optical sizes rather than one scaled drawing:

| File | Use | Detail |
|---|---|---|
| `static/brand/mark.svg` | 48px and up: header, empty states, README | Full glyph, cut visible |
| `static/brand/mark-small.svg` | 16–32px: favicon | Thicker brackets, no cut (a 1px gap disappears at 16px), triangle enlarged |
| `static/brand/logo.svg` | Lockups: README, install screens | Mark plus "Supercut" wordmark |

**Why a filled tile**: a glyph drawn straight on a transparent background is designed for
one background. Browsers' tab strips are light or dark independently of the page and of
the OS. An SVG favicon's `prefers-color-scheme` follows the OS, not the browser's tab
strip, so it can't fix this. A white glyph on its own gradient tile reads the same on
any strip (User Story 1 scenario 3, SC-001). White on the tile's violet end measures
6.12:1.

**Alternatives rejected**:

- *A face silhouette*: reads as a contacts or avatar app, and is muddy at 16px.
- *Scissors*: generic "cut", says nothing about finding a person.
- *Film strip*: reads as "video" and is busy at small sizes.

---

## D6. Icons and installability: PNGs rendered once and committed; manifest; Apple meta

**Decision**: Ship these in `static/brand/`:

| File | Size | Purpose |
|---|---|---|
| `favicon.svg` | vector | Modern browsers |
| `favicon-32.png` | 32px | Safari and fallback |
| `apple-touch-icon.png` | 180px | iOS home screen. Rendered **opaque** from the full-bleed `mark-maskable.svg`: iOS applies its own corner mask and fills transparency with black. |
| `icon-192.png`, `icon-512.png` | 192, 512px | Manifest |
| `icon-maskable-512.png` | 512px | Android adaptive icons; opaque, from `mark-maskable.svg`, glyph inside the 80% safe zone |

Add `static/manifest.webmanifest`:

- `name: "Supercut"` and `short_name: "Supercut"`
- `display: "standalone"`
- `theme_color` set to the violet, `background_color` to the dark page background

Pages carry the `<link rel="icon">`, `apple-touch-icon` and `manifest` tags, plus
`<meta name="theme-color">` in both light and dark variants (via its `media` attribute).
They also carry `apple-mobile-web-app-capable` and `apple-mobile-web-app-title`.
`/favicon.ico` is answered with the 32px PNG, because browsers request it whatever the
page says.

PNGs are rendered from the SVGs **once, by the developer**, with headless Chrome.
`tools/render-icons.sh` records the command, and the PNGs are committed.

**Rationale**:

- Nothing on this machine rasterises SVG except Chrome. `ffmpeg` here has no librsvg,
  and no Pillow is installed.
- Adding a Python rasteriser to `requirements.txt` would put a runtime dependency in the
  image for a build-time job (Principle IV).
- The icons change approximately never.

**Install over plain HTTP (Principle III)**: iOS "Add to Home Screen" honours
`apple-mobile-web-app-capable` on any origin and opens standalone. Android Chrome only
installs a standalone app on a **secure origin**. On `http://<host>:8765` it creates a
shortcut that opens in a browser tab. Development on `localhost` *is* a secure origin, so
it would show full install there and mislead. This is the same divergence that D9
records for notifications. The spec's User Story 1 scenario 4 and FR-033a now say "where
the browser allows it". The quickstart tests installation against the deployment, not
localhost.

---

## D7. YouTube previews: thumbnails straight from YouTube, titles through a server-side oEmbed lookup

**Decision**:

- **Video id**: `shell.js` exports `youtubeId(url)`. It recognises `watch?v=`, `youtu.be/`,
  `/shorts/`, `/live/` and `/embed/` on `www.`, `m.` and `music.` hosts. It returns the
  11-character id or `null`.
- **Thumbnails**: loaded by the browser from `https://i.ytimg.com/vi/<id>/mqdefault.jpg`.
  On `error` they fall back to a branded placeholder (FR-026).
- **Titles**: fetched from a new `GET /api/youtube/preview?url=...` (see
  [contracts/http.md](./contracts/http.md)). The server:
  - extracts and validates the id against `^[A-Za-z0-9_-]{11}$`
  - builds the oEmbed URL itself, as `https://www.youtube.com/oembed?format=json&url=https://www.youtube.com/watch?v=<id>`
  - fetches it with stdlib `urllib` and a 4-second timeout
  - caches results in memory (256 entries)
  - answers `200` with `title: null` on any failure
- **Client**: debounces 400 ms after the last keystroke. Recognition never blocks submit
  (FR-025).

**Rationale**:

- Thumbnails need no server involvement. `i.ytimg.com` is public and cacheable.
- Titles do need the server. Whether the oEmbed endpoint sends CORS headers is not
  something to build a feature on.
- Never fetching a user-supplied URL rules out the endpoint being used to make the server
  request arbitrary addresses, without having to sanitise anything (Principle V's
  "validate, never sanitise").
- oEmbed is one small HTTP request. Using yt-dlp for this would take seconds and compete
  with the running job on a four-core box.
- An in-memory cache is safe under the single-process rule.

**Verify in the container (Principle III)**: the image's network path to `youtube.com` is
the one yt-dlp already uses. The quickstart includes one preview call made against the
deployment.

**Alternatives rejected**:

- *yt-dlp `--get-title`*: slow and heavy, as above.
- *Browser-side oEmbed fetch*: depends on CORS behaviour we don't control.
- *No title, thumbnail only*: the spec asks for the title "where available". The cost is
  one small endpoint.

---

## D8. Starting from the home page: create, then hand the link over in the query string

**Decision**: The home page's start field validates that the input is URL-shaped, then:

1. calls the existing `POST /api/sessions`
2. navigates to `/session/<id>?url=<encoded>`

On load, the session page:

1. reads the `url` parameter
2. puts it into the add-video URL field
3. starts the preview (D7)
4. removes the parameter with `history.replaceState`, so a reload doesn't re-insert a
   link the user has since cleared
5. focuses the screenshot drop zone, so the very next paste lands there

The existing "Create session" button stays (FR-021).

**Rationale**:

- No API change.
- A session is only created by an explicit submit, as today.
- The query string survives the navigation without browser storage, so it works in a
  private window too.
- Focusing the drop zone is what makes SC-004's three actions possible.

**Alternatives rejected**:

- *A new endpoint that creates a session and adds a video at once*: it would need the
  screenshot on the home page too, duplicating the add-video form.
- *Passing the link through `sessionStorage`*: breaks in private windows (spec edge case).

---

## D9. Notifications, share and clipboard need a secure origin, and the deployment isn't one

**Finding**: The Notifications API, `navigator.share` and `navigator.clipboard` are all
**secure-context only**. The deployment is `http://<host>:8765` on the LAN, which is not
a secure context. `http://127.0.0.1`, where development happens, is.

So all three would work on the developer's machine and silently do nothing in production.
This is Principle III's failure mode exactly, and it explains why the existing session-id
Copy button has a "Copy failed" path.

**Decision**:

- **Notifications**: the offer (FR-033) appears only when `window.isSecureContext &&
  "Notification" in window`. Where permission was already `"denied"`, the offer explains
  how to re-enable it instead of showing a dead button. Elsewhere, nothing is shown. Tab
  title and favicon progress (D10) are the background signal on HTTP.
- **Share**: the button appears only when `navigator.share` exists and `canShare` accepts
  the URL.
- **Copy**: `shell.copyText()` tries `navigator.clipboard.writeText` first. Off a secure
  origin it falls back to selecting a hidden `<textarea>` and `document.execCommand("copy")`.
  That method is deprecated but still supported everywhere, and is the only copy that
  works on plain HTTP. The session-id Copy button moves onto the same helper.

**Recorded for the owner**: putting the app behind HTTPS would light up notifications,
share and full Android install with no code change, for example with a reverse proxy or
Tailscale's HTTPS on the tailnet name. That is a deployment decision, outside this
feature, and the README states it.

**Alternatives rejected**:

- *Service-worker push*: also secure-context only, and needs a push service.
- *Hiding the features entirely*: they work on `localhost` and would work behind HTTPS.
  Gating on capability serves both.

---

## D10. Background progress: tab title and favicon, fed by a slow hidden-tab poll

**Decision**: `progress.js` keeps its 1-second poll while visible. While hidden, it no
longer stops: it polls **every 10 seconds** instead.

On each update, `shell.js` subscribes and does three things:

- **Title**: sets `document.title` to `"42% · Scanning · Supercut"` while processing, and
  restores the page's own title otherwise.
- **Favicon**: redraws a 64×64 canvas, with the mark plus a progress arc around it in the
  gradient, and swaps it into the icon `<link>`. It redraws only when the percentage moves
  by a whole point or the stage changes.
- **Notifications**: fires the FR-034 notification on the transition into a terminal
  state.

**Why this reverses 002 research D2**:

- 002 suspended hidden polling so that "five tabs pay five requests a second forever"
  wouldn't happen. That reasoning is sound, but it assumed nothing needed a hidden tab to
  stay current.
- FR-031 (title and favicon) and FR-034 (notifications) are only useful *because* the tab
  is hidden.
- At 10 seconds, five hidden tabs cost one request every two seconds, against a handler
  that reads an in-memory dict. 002 itself called that noise.
- 10 seconds is chosen, not measured: it is the slowest rate at which a glance at the tab
  still feels current. The spec's FR-045 and SC-008 were amended to permit and reflect it.

**Browser throttling, accepted**: Chrome slows chained timers in pages hidden for more
than 5 minutes to about once a minute. So a long-hidden tab updates about every minute,
whatever we ask for. SC-008 states this.

Server-sent events would avoid timers. They were rejected again, for a reason 002 didn't
need: on plain HTTP/1.1 a browser allows only **6 connections per host**. Each tab's
event stream would hold one open, so the seventh tab would hang. That is a realistic
number here, since every page of the app counts.

**Safari**: it does not reliably repaint dynamically changed favicons. The title prefix
is the primary signal and works everywhere. The favicon is an enhancement.

---

## D11. Elapsed time measured by the server, ticked by the client

**Decision**: `SessionStore` records `started: time.monotonic()` in the in-memory
`_runtime` entry when `pick_next` starts a video or a join. `snapshot()` and `active()`
then include `elapsed_s`, computed server-side. The client shows it and adds one second
per second between polls, re-syncing on each response.

**Rationale**:

- The phone's clock and the server's can disagree by minutes. A server-computed duration
  makes that irrelevant.
- `_runtime` is in-memory, and that is right: a restarted video starts over (spec 003
  FR-020), so its elapsed time *should* reset.
- No change to `session.json`.

**Not an ETA**: the spec's assumptions rule out an estimate, since nothing measured
supports one (Principle II).

---

## D12. Celebration, keyed by completion rather than by session

**Decision**:

- **Effect**: on the session page, the finished-reel presenter enters with a short
  scale-and-fade (400 ms). A burst of about 36 gradient-coloured particles fires on a
  `<canvas>` overlay and ends within 1.6 seconds (both chosen, not measured). There is no
  sound. Under `prefers-reduced-motion` the particles are skipped and the presenter
  appears with a fade.
- **Once**: it is keyed by **completion**, not session: `"<session id>@<completed_at>"`.
- **Bar notice**: the notice's acknowledgement moves to the same key. `/api/jobs/active`'s
  terminal payload gains `completed_at` so the bar can build it.
- **Storage**: celebrated keys are a small capped list (last 50) in
  `localStorage["supercut.celebrated"]`.
- **Dismissed notice**: if the bar's notice for that completion was already dismissed,
  the celebration doesn't play (spec edge case).

**Rationale**: `retry_failed()` clears `completed_at` and the re-join sets a new one. A
key including it gives a rebuilt reel its own celebration, as the spec requires.

**Existing bug this fixes**: today's acknowledgement is keyed by session id alone. After
a retry rebuilds a reel, the bar's "Session reel ready" notice never reappears, because
that session was already acknowledged. Moving the key fixes it for free. The commit says
so, so the fix isn't invisible.

**Migration**: `progress.js` reads `facereel.acknowledged` once. If it holds the current
terminal session's id, `progress.js` treats that completion as acknowledged and writes it
under the new key. It then deletes the old key, so a notice the user had dismissed doesn't
pop back up on the first load after the deploy.

---

## D13. Clip navigation: probe each cut segment, and keep native controls

**Decision, data**: `cut_and_stitch()` runs `ffprobe -show_entries format=duration` on
each segment after cutting it and before deleting it. Clip starts are the running total.
`process_job()` returns `clips: [{start, end, source_start}]`, with times in seconds,
rounded to 0.01. `archive_job()` writes it to `reel.json`.

For a session reel:

1. `join_reels()` returns `offsets`, each input's start time in the joined reel. These are
   the running total of the probed durations of the files actually concatenated: the
   normalised files on the re-encode path, which it probes once more.
2. `Runner._run_join()` shifts each joined video's own `clips` by its offset and tags them
   with `video` (id), `index` and `title`.
3. A video whose reel predates this feature has no `clips`. It contributes one clip
   spanning its whole stretch, marked `whole: true`. Its stretch is still labelled with
   the source video (FR-042), just without inner marks.

**Why probe instead of summing `end - start`**: the concat demuxer offsets each file by
that file's container duration, not by the requested `-t`. Re-encoding rounds every
segment to whole frames, and AAC priming adds audio. A nominal sum drifts by up to about
a frame per clip, which is over 3 seconds across a 100-clip reel. A probe reads the
number the demuxer actually uses, so the marks land exactly.

**Cost**: one `ffprobe` per segment, on files a few seconds long. This is the only work
this feature adds to the pipeline. It will be **measured on the nucbox** for a reel of
about 50 clips, with the figure recorded in the code comment (Principle II, task in
tasks.md). The expectation is tens of milliseconds per probe against minutes of encoding.
If it turns out otherwise, the fallback is the nominal sum, with its drift documented.

**Decision, UI**: the reel keeps the browser's native `<video controls>`. Rebuilding
seek, volume, fullscreen and picture-in-picture would be a lot of surface to get subtly
worse. Below the video, `player.js` renders a **clip strip**:

- one segment per clip, with width proportional to its duration
- for session reels, coloured and labelled by source video
- the current clip highlighted from `timeupdate`
- clicking a segment seeks to it
- previous and next buttons, with `[` and `]` as shortcuts while the player has focus

For session reels, hovering or focusing a segment shows the video's title (FR-042).
Reels without `clips` render no strip (FR-043).

**Where the session page gets it**: a new `GET /api/archive/<id>` returns one entry,
including `clips`, so the page doesn't fetch the whole archive listing. The archive
listing carries `clips` automatically, because `list_entries` passes sidecar fields
through.

**Alternatives rejected**:

- *Custom video controls with marks on the scrubber*: too much surface, as above.
- *WebVTT chapters*: browsers don't render chapter marks on native controls.
- *Clip map only on new single reels*: session reels are the main output, and their
  per-video stretches are recoverable even from old parts.

---

## D14. Static assets: one allow-listed route, no `StaticFiles` mount

**Decision**: Replace the `/static/progress.js` route with `GET /static/{path:path}`.
It serves only paths found in an allow-list. The allow-list is built at start-up by
walking `static/css`, `static/js` and `static/brand`, plus `static/progress.js`,
`static/icons.svg` and `static/manifest.webmanifest`. Anything else returns 404, so the
`.html` pages are not served raw.

Responses carry `Cache-Control: no-cache`, as every page and `progress.js` already do.
The media type comes from the extension, with `.webmanifest` mapped to
`application/manifest+json`.

Two further routes:

- `/favicon.ico` serves `brand/favicon-32.png`.
- `/manifest.webmanifest` serves the manifest. Some installers look for it at the root.

**Rationale**:

- The comment on today's `progress_js()` explains the stale-copy hazard after redeploys.
  Starlette's `StaticFiles` sends no `Cache-Control`, so it would bring the hazard back
  for every new asset.
- Building the allow-list from the files on disk validates the requested path against an
  explicit set before any filesystem path is built, instead of sanitising it afterwards
  (Principle V).
- `no-cache` still allows 304 revalidation, so the PNGs aren't re-downloaded. Over the
  LAN, a revalidation costs about a millisecond.

**Alternatives rejected**:

- *`StaticFiles` with a middleware adding headers*: two mechanisms where one route does.
- *Inlining everything into each page*: defeats D1.

---

## D15. Accessibility mechanics

**Decision**:

- **Announcer**: `shell.js` owns one visually hidden `aria-live="polite"` region.
  `announce()` is called on stage changes, state changes, toasts and completions, never
  on percentage ticks (FR-015).
- **Status badges**: icon plus text label (FR-009).
- **Focus**: every interactive element shows `:focus-visible` as a 2px ring in `--focus`,
  offset 2px (FR-010).
- **Modals and confirmations**: native `<dialog>`, which brings focus trapping and Escape
  for free. Browser `alert`, `confirm` and `prompt` are banned (FR-013).
- **Touch targets**: `@media (pointer: coarse)` raises the minimum to 44px (FR-012).
- **Reduced motion**: every `transition` and `animation` lives under `@media
  (prefers-reduced-motion: no-preference)`. Motion is opt-in, so FR-011 holds by
  construction rather than by remembering to opt out.

---

## D16. Motion: View Transitions between pages, as an enhancement

**Decision**: `@view-transition { navigation: auto; }` is in the stylesheet, under the
reduced-motion guard. The header gets `view-transition-name: header`, so it holds still
while content cross-fades between Sessions, a session, and the Archive. A reel card and
the viewer share a `view-transition-name`, so opening a reel grows the card into the
player.

Browsers without cross-document View Transitions (Firefox as of this writing) simply
navigate.

**Rationale**: It is the single highest "feels like a product" effect per line of code,
and it costs nothing where unsupported.

---

## D17. What gets renamed, and what deliberately doesn't

| Surface | Change |
|---|---|
| Page titles, headings, header, copy, manifest, Apple meta | → Supercut |
| FastAPI `title` | → Supercut |
| New session reels' `filename` (`archive_session`) and the session page's `download` attribute | `facereel-session-<id>.mp4` → `supercut-session-<id>.mp4` |
| Existing archived sidecars | **Not rewritten.** A sidecar is a record of what was made. Old reels keep their stored file names. |
| `progress.js` element id, global (`window.FaceReelProgress` → `window.SupercutProgress`), storage keys | Renamed, with the one-time key migration in D12 |
| README, HANDOFF.md | Name updated, with "formerly FaceReel" noted once. Deployment instructions keep the real image and path names. |
| Constitution heading "FaceReel Constitution" | → "Supercut Constitution". A PATCH amendment (1.0.1) with a Sync Impact Report. |
| Image `ghcr.io/deshsa01/facereel`, compose service and container name, `/opt/facereel/storage`, GitHub repo | **Unchanged** (spec assumption). Renaming them would break the running Portainer stack and buy the user nothing. |

---

## D18. Verification without a test framework

**Decision**: As the constitution allows, there is no test framework. Verification is:

- the contrast script (D3), re-run on any token change
- the [quickstart](./quickstart.md), with every step tagged by the environment it runs in
- an FR-044 parity walk-through on the deployment

The two pieces of new pure logic are written as plain functions so a test could be added
later without restructuring: offsetting clip maps in the runner, and the YouTube id
parser in `shell.js`.
