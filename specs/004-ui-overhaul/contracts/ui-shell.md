# UI Shell Contract: Supercut

What every page must contain, and the browser-side API that `shell.js`, `progress.js` and
`player.js` provide to page scripts. Page scripts rely on these and nothing else that is
shared.

---

## 1. Page skeleton (all three pages)

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{Page} · Supercut</title>
<meta name="description" content="Every moment they appear, cut into one reel.">
<!-- theme: must run before the stylesheet; identical in index/session/archive.html (research D2) -->
<script>try{var t=localStorage.getItem("supercut.theme");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}</script>
<link rel="stylesheet" href="/static/css/supercut.css">
<link rel="icon" href="/static/brand/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/static/brand/favicon-32.png" sizes="32x32" type="image/png">
<link rel="apple-touch-icon" href="/static/brand/apple-touch-icon.png">
<link rel="manifest" href="/manifest.webmanifest">
<meta name="theme-color" content="#F6F6FA" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#0A0A10" media="(prefers-color-scheme: dark)">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Supercut">
</head>
<body data-page="sessions|session|archive">
  <a class="skip-link" href="#main">Skip to content</a>
  <header class="app-header"> … see §2 … </header>
  <main id="main"> … page content … </main>
  <script src="/static/js/shell.js"></script>
  <script src="/static/progress.js"></script>
  <!-- page-specific: <script src="/static/js/player.js"></script> on session and archive -->
  <script> … page script … </script>
</body>
</html>
```

`shell.js` loads before `progress.js`, because it subscribes to the bar's updates.

## 2. Header

Static markup in each page, not injected, so it costs no layout shift. Its
`view-transition-name` is `header`.

- **Left**: the mark (`mark.svg`, 28px) and the wordmark "Super**cut**", where "cut"
  carries the gradient. It links to `/`.
- **Centre/right**: nav links **Sessions** (`/`) and **Archive** (`/archive`). The current
  one carries `aria-current="page"` and an accent underline.
- **Right**: the theme control. It is a button showing the current mode's icon (sun,
  moon, or monitor for System). It opens a popover menu of three options with
  `role="menuitemradio"` and `aria-checked`. On a narrow screen it stays an icon button.

## 3. `window.Supercut` (from `shell.js`)

| Member | Contract |
|---|---|
| `theme.get()` → `"light"\|"dark"\|"system"` | The current preference. |
| `theme.set(mode)` | Writes `supercut.theme` (inside `try`), updates `data-theme`, and updates the header control. Other tabs follow through the `storage` event. |
| `toast(message, {kind = "info"\|"success"\|"error", action?: {label, onClick}, timeout = 5000})` | Shows a toast in a bottom-right stack (bottom-centre on narrow screens) above the progress bar, with a dismiss button. Errors stay up until dismissed. Also calls `announce`. |
| `announce(text)` | Writes to the single `aria-live="polite"` region. Callers announce changes of stage or state, never percentages (FR-015). |
| `copyText(text)` → `Promise<boolean>` | The clipboard API on a secure origin, otherwise the `execCommand` fallback (research D9). Never throws. |
| `canShare(url)` → `boolean`; `share({title, url})` | Share-sheet support detection, and sharing (FR-035). |
| `youtubeId(url)` → `string\|null` | Research D7. A pure function. |
| `youtubeThumb(id)` → `string` | `https://i.ytimg.com/vi/<id>/mqdefault.jpg`. |
| `thumbImg(url, alt)` → `HTMLElement` | A thumbnail element with a branded placeholder on error or when there's no id (FR-026). |
| `faceChip(src, label)` → `HTMLElement` | A round screenshot crop with its label ("Looking for", or "Same as video 2"). |
| `badge(state, label)` → `HTMLElement` | A status badge with an icon and text (FR-009). |
| `stageTrack({stage, progress, elapsed_s, zoom, network})` → `HTMLElement` | Data-model §7 stage track. Calling `update(sameArgs)` on the returned element updates it in place. |
| `fmtDuration(s)`, `fmtBytes(n)`, `fmtDate(iso)` | The shared formatters (deduplicated from the pages). |
| `icon(name)` → `SVGElement` | `<svg><use href="/static/icons.svg#i-<name>"/></svg>`, with `aria-hidden`. |
| `notify.available()` → `boolean` | `isSecureContext && "Notification" in window`. |
| `notify.state()` → `"unavailable"\|"blocked"\|"accepted"\|"declined"\|"ask"` | Combines `notify.available()`, `Notification.permission` and `supercut.notify`. |
| `notify.offer(container)` | Renders the one-time in-page offer into `container` when the state is `"ask"`. A "blocked" explainer is rendered when the state is `"blocked"`, and nothing otherwise. Accepting calls `Notification.requestPermission()` **from inside the click handler**. |
| `celebrate(targetEl)` | Research D12. Does nothing under reduced motion except a fade on `targetEl`. |
| `celebrated.has(key)`, `celebrated.add(key)` | The capped completion-key list (data-model §5). |

Tab title and favicon progress (research D10) are wired internally from
`SupercutProgress.subscribe`, so page scripts don't call them. Pages set their base title
through `document.title` as usual. `shell.js` records it as the base and adds or removes
the `NN% · Stage · ` prefix around it.

## 4. `window.SupercutProgress` (from `progress.js`)

| Member | Contract |
|---|---|
| `subscribe(cb)` | `cb(job)` on every poll result, with `job` exactly as returned by `GET /api/jobs/active` (`null` when idle). Unchanged semantics, renamed from `FaceReelProgress`. |
| `completionKey(job)` → `string\|null` | `"<session_id>@<completed_at>"` for terminal payloads, otherwise `null` (data-model §3). |
| `isAcknowledged(key)` | Whether the bar's notice for that completion was dismissed. |

Polling: every 1 s while visible, every 10 s while hidden (research D10). Two consecutive
failures mark it stale (unchanged).

Bar layout: a condensed stage track, a "Session 4f2a91… · video 2 of 5" line, the
percentage, elapsed time and an "Open session" link. It reserves its own height on
`body` (unchanged mechanism).

## 5. `window.SupercutPlayer` (from `player.js`)

| Member | Contract |
|---|---|
| `attach(videoEl, entry)` → `{destroy()}` | When `entry.clips` is a non-empty array, inserts the clip strip after `videoEl` and binds `timeupdate`, segment clicks, the previous/next buttons and the `[`/`]` keys (only while focus is in the player or strip). Otherwise it inserts nothing and returns a no-op handle (FR-043). |

Strip rules:

- Each segment's width is proportional to `end - start`, with a 3px minimum, so a
  half-second clip is still clickable.
- For session reels, segments are tinted by `index`, cycling through 6 tints derived from
  the gradient. A thin divider marks each video boundary.
- Each segment is a `<button>` with an accessible name: "Clip 3 of 12, 0:42" for single
  reels, and "Clip 3 of 12, from video 2: <title>, 0:42" for session reels.

## 6. Shared components (in `supercut.css`)

Every page uses these classes. No page restyles them (FR-008).

| Class | Variants |
|---|---|
| `.btn` | `.btn-primary`, `.btn-secondary`, `.btn-quiet`, `.btn-danger`, `.btn-sm`, `.btn-icon` |
| `.field`, `.input` | `.input-lg` (home start field), with an inline leading icon |
| `.dropzone` | `.is-dragover`, `.has-file`, `.is-error` |
| `.toggle` | a switch built on `<input type="checkbox" role="switch">` |
| `.slider` | a styled `<input type="range">` with a value bubble |
| `.card` | `.card-media` (16:9 media top), `.card-interactive` |
| `.badge` | `.is-waiting`, `.is-processing`, `.is-done`, `.is-failed`, `.is-removed`, `.is-network`, `.is-session` |
| `.stage-track` | `.is-paused` (network wait) |
| `.toast-stack`, `.toast` | `.is-success`, `.is-error` |
| `dialog.modal` | `.modal-viewer` (archive lightbox), `.modal-confirm` |
| `.empty` | an illustration slot, title, body and action |
| `.skeleton` | `.skeleton-text`, `.skeleton-thumb`, `.skeleton-row` |
| `.face-chip` | `.is-reused` |
| `.thumb` | `.is-placeholder` |
| `.meter` | the archive storage meter |
| `.clip-strip` | `.clip-seg`, `.is-current` |
| `.reel-presenter` | the finished-reel hero (gradient frame, `--glow`) |

## 7. Page compositions

**Sessions (`/`)**

1. **Hero**: the headline "Every moment they appear. One reel.", one line of explanation,
   and the **start field** (`.input-lg`, a link icon, placeholder "Paste a YouTube link
   to start") with a **Start** button. Beneath it sits a quiet "or create an empty
   session" button (FR-021).
2. **Now processing**: shown only while something processes, fed by `SupercutProgress`
   (no new polling). It has the video thumbnail, session and video label, stage track and
   elapsed time.
3. **Running sessions**: cards with a thumbnail strip (up to 4, from `video_urls`), the
   title, the counts as badges, the started time and a **Join** button. While loading it
   shows skeleton cards. With no sessions, the section is hidden: the hero is the empty
   state.
4. **Recent reels**: the 6 newest archive entries as small media cards, fetched once on
   load (not polled), with "View all →" to `/archive`. Hidden when the archive is empty.

**Session (`/session/<id>`)**

- **Header row**: the session title or "New session", the short id with a copy button,
  and the "N of 10 videos" meter.
- **Finished**: `.reel-presenter` at the top, full width. It holds the video, the clip
  strip, stats chips (duration, clips, resolution, videos joined), **Download**,
  **Copy link**, **Share** (when available), and "Start a new session". It also holds the
  retry button when some videos failed.
- **Open**: two columns at ≥ 960px, stacked below that.
  - **Left, the add-video composer**:
    - the URL field with a live preview card (thumbnail and title)
    - the dropzone, which becomes a face chip once filled, with click, drop and paste
    - the zoom and 4K toggles and the outcome line
    - the "Advanced" disclosure with the existing tuning
    - the submit button
  - **Right**: the queue.
- **Joining**: a progress card with the gradient bar and elapsed time.
- **Notices**: "Finishes after this video" (warning tint), the notification offer (once),
  and "Session not found" (an empty state with a link home).

**Archive (`/archive`)**

1. **Toolbar**: a search input (leading icon, clear button), segmented kind filter (All ·
   Sessions · Single videos), a sort menu, and the storage meter on the right ("23 reels
   · 4.2 GB").
2. **Grid**: `.card-media` reel cards with:
   - the poster
   - a duration chip, bottom-right on the poster
   - a Session badge where it applies
   - an Unavailable badge where it applies
   - title, date and size
   - hover or focus preview (research D13; the 250 ms delay is in the design tokens)
3. **Viewer**: `dialog.modal-viewer` showing the large video, the clip strip and metadata.
   It also has the "Joined" and "Not included" lists, "From session" link, Download, Copy
   link, Retry failed and Delete. Delete opens `dialog.modal-confirm`. It has previous and
   next arrows, and the ← → and Esc keys.
4. **Empty states**: "No reels yet" (links to Sessions), and "Nothing matches" (clears the
   search and filters).
