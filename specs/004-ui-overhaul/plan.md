# Implementation Plan: UI/UX Overhaul and Rebrand to Supercut

**Branch**: `004-ui-overhaul` | **Date**: 2026-10-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/004-ui-overhaul/spec.md`

## Summary

Rename FaceReel to **Supercut** and give it an identity:

- a "cut frame" logo
- a favicon that reads on any tab strip
- home-screen icons and a web manifest

Rebuild all three pages on one design system: a single shared stylesheet of tokens and
components, a small shared script, and native platform features (`light-dark()`,
`<dialog>`, popovers, View Transitions). There is no framework and no build step. The
look is an electric-violet-to-coral brand over neutral surfaces that are designed
separately for light and dark. Every text and control colour pair is measured against
WCAG AA.

Add a Light/Dark/System theme control that never flashes, a paste-first add-video flow
with YouTube previews and a face chip, a stage-by-stage progress track with elapsed time,
progress in the tab title and favicon, a once-per-completion celebration, and capability-gated
notifications and sharing. The archive becomes a searchable gallery with hover previews,
keyboard navigation and a storage meter. Reels gain a clip map, recorded at stitch time by
probing each cut segment, which drives a clip strip under the player.

The server changes are small and additive:

- an allow-listed static route
- an oEmbed title lookup that never fetches user input
- a single-entry archive route
- `elapsed_s`, `completed_at` and `video_urls` fields on existing responses
- the clip map

How reels are made and how the queue is served is unchanged.

The most consequential research finding: notifications, share and the clipboard API need
a secure origin. The deployment (plain HTTP on the LAN) isn't one, but `localhost` is. So
these features are gated on capability, and they are verified against the deployment, not
the dev machine (research D9).

## Technical Context

**Language/Version**: Python 3.14 (server, unchanged); HTML, CSS and JavaScript (ES2022), with no transpilation.

**Primary Dependencies**: FastAPI and uvicorn (existing, unchanged). **No new runtime dependencies**, Python or JavaScript. Icons are a vendored SVG sprite (static assets, licence noted in the file). Headless Chrome is used once, at development time, to render PNG icons (research D6). It is not in the image.

**Storage**: Files, unchanged layout. `reel.json` gains an optional `clips` array (data-model §1). Per-browser preferences live in `localStorage` (data-model §5).

**Testing**: No test framework (constitution, Development Workflow). Verification is [quickstart.md](./quickstart.md), with environment-tagged steps, the [`contrast.py`](./contrast.py) measurement, and an FR-044 parity walk-through.

**Target Platform**: Linux container on the nucbox (Intel N95), served over plain HTTP on the LAN. Clients are current Safari (macOS, iOS 17.5+), Chrome or Edge 123+, and Firefox 120+. Older browsers get the light theme and remain functional.

**Project Type**: Single-process web application (FastAPI serving static pages and a JSON API).

**Performance Goals**: Meaningful content within 1 s on the LAN (SC-007). The shared CSS is ≤ 40 KB, `shell.js` plus `player.js` ≤ 40 KB, and the icon sprite ≤ 15 KB, all uncompressed. Clip-map probing must add a negligible fraction to stitch time, to be measured on the nucbox (research D13).

**Constraints**:

- Single instance and single worker (the in-memory oEmbed cache relies on it).
- Visible polling rates unchanged. Hidden tabs poll at most every 10 s (amended FR-045).
- No work added to the pipeline beyond `ffprobe` per segment.
- Plain-HTTP deployment: secure-context APIs are capability-gated.
- `prefers-reduced-motion` honoured by construction.

**Scale/Scope**: One user, a handful of devices, and three pages. The archive is expected to reach hundreds of reels, all filtered client-side from one listing. Sessions hold at most 10 videos.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment | Status |
|---|---|---|
| **I. Explain Why, Not What** | Every chosen constant gets a comment saying it is chosen and why: 10 s hidden poll, 250 ms preview delay, 1.6 s celebration, 50-key cap, 4 s oEmbed timeout, 256-entry cache. So do the ordering hazards: the inline theme script before the stylesheet, the `GET /api/archive/{id}` route after its siblings, and `shell.js` before `progress.js`. The repeated head script names its other copies. | PASS (obligation carried into tasks) |
| **II. Measure Before Tuning** | Contrast is **measured** (research D3), and one candidate failed and was replaced as a result. The clip-map approach was chosen *because* nominal sums would drift (D13), and its cost is to be **measured** on the nucbox before merge. Presentation timings have no measurement that could apply. They are marked as chosen, following the archive's `THUMB_*` precedent. No ETA is shown, because nothing measured supports one. | PASS, with one measurement owed (quickstart §7.4) |
| **III. Verify In The Environment That Ships** | The decisive finding: secure-context APIs work on `localhost` and not on the LAN deployment (D9). Android install has the same split (D6). The quickstart tags every step [local], [deploy] or [phone]. The capability-dependent steps and the container's route to YouTube oEmbed are [deploy] only. | PASS |
| **IV. Earn Every Dependency** | No packages added. Rejected with reasons: a frontend framework, Tailwind, a web font, a Python SVG rasteriser, SSE, and `StaticFiles` (D1, D4, D6, D10, D14). Headless Chrome is a development-time tool, recorded in `tools/render-icons.sh`. | PASS |
| **V. Destructive Operations Are Explicit And Bounded** | No new deletion. The existing archive delete keeps its confirmation, moved from browser `confirm` styling into `<dialog>`. Inputs that reach a path or a fetch are validated against explicit patterns before use: the static route's allow-list (D14), and the oEmbed id regex, with the server building the URL itself (D7). Existing sidecars are never rewritten (D17). | PASS |
| **Runtime: single instance** | The oEmbed cache is per process, which is correct under the rule. No shared state is added. | PASS |
| **Runtime: durable data under `storage/`** | `clips` lives in the existing sidecar. Everything else new is either static assets in the image or browser-side. | PASS |
| **Runtime: modest host** | Request-path additions: a cached oEmbed lookup and a slow hidden poll that reads an in-memory dict. Pipeline addition: `ffprobe` per segment, to be measured. | PASS, measurement owed |
| **Workflow: documentation must not outlive its truth** | README and HANDOFF.md are renamed and gain the new behaviours: start-from-home, hidden-tab polling, the HTTPS note, and the browser floor. The constitution heading changes in a PATCH amendment (D17). | PASS (tasks) |
| **Workflow: report honestly** | The pre-existing bug (retry-rebuilt reels never re-announce, D12) is fixed in this change, and the commit says so. | PASS |

**Post-design re-check** (after Phase 1): unchanged, all PASS. Phase 1 introduced no new
dependency or destructive path. Two obligations remain open and are tracked: measuring the
probe cost (II), and running the [deploy] steps (III).

## Project Structure

### Documentation (this feature)

```text
specs/004-ui-overhaul/
├── spec.md               # amended in planning: FR-033a, FR-045, SC-008, US1 scenario 4
├── plan.md               # this file
├── research.md           # D1–D18
├── data-model.md         # clip map, timers, completion key, preferences, view states
├── quickstart.md         # environment-tagged validation
├── contrast.py           # the D3 measurement, re-runnable
├── contracts/
│   ├── http.md           # route and response changes; Python seam changes
│   ├── design-tokens.md  # the token set
│   └── ui-shell.md       # page skeleton, shell/progress/player APIs, components, page compositions
├── checklists/requirements.md
└── tasks.md              # /speckit-tasks (not created here)
```

### Source Code (repository root)

```text
app.py                    # + /static/{path} allow-list route, /favicon.ico, /manifest.webmanifest,
                          #   /api/youtube/preview, /api/archive/{id}, disk figures on /api/archive;
                          #   title → Supercut
archive.py                # + clips in sidecars, read_public_entry(), supercut-session- filename
pipeline.py               # cut_and_stitch probes segments → clips; join_reels → offsets
runner.py                 # builds session clip map from offsets + per-video clips
sessions.py               # started on _runtime; elapsed_s, completed_at, video_urls on read side
youtube.py                # NEW: id extraction + validated oEmbed lookup + LRU cache (stdlib only)

static/
├── index.html            # rewritten: hero start field, now-processing, sessions, recent reels
├── session.html          # rewritten: composer + queue, presenter, celebration
├── archive.html          # rewritten: toolbar, gallery, viewer dialog
├── progress.js           # restyled; stage track; 10 s hidden poll; completion keys; renamed globals
├── icons.svg             # NEW: symbol sprite
├── manifest.webmanifest  # NEW
├── css/supercut.css      # NEW: tokens, base, components, motion
├── js/shell.js           # NEW: window.Supercut
├── js/player.js          # NEW: window.SupercutPlayer (clip strip)
└── brand/                # NEW: mark.svg, mark-small.svg, mark-maskable.svg, logo.svg, favicon.svg,
                          #   PNG icons, empty-state illustrations

tools/render-icons.sh     # NEW: headless-Chrome SVG→PNG, run by hand when the logo changes

README.md, HANDOFF.md     # rename + new behaviours
.specify/memory/constitution.md   # PATCH 1.0.1: heading rename
```

**Structure Decision**: Keep the existing flat single-project layout. The Python modules
stay at the root, and pages stay in `static/`. New shared front-end code goes into
`static/css`, `static/js` and `static/brand`, so the allow-list route (research D14) can be
defined by directory.

`youtube.py` is a new module rather than code added to `app.py`. It does network I/O with
its own cache and validation rules, and isolating it keeps the SSRF-relevant code in one
reviewable place.

## Delivery order

The order follows the user-story priorities. Each step is independently shippable, so the
app is never half-restyled on `main`. Each step can be its own commit and deploy:

1. **Foundation**: tokens, components, `shell.js` core, brand assets, the static route,
   and the header on all three pages, with existing behaviour restyled only. Covers US1,
   US2 and FR-044 parity.
2. **Theme control**: covers US3. It is mostly in place after step 1, so this adds the
   control, persistence and cross-tab sync.
3. **Composer and progress**: covers US4 and US5.
   - start-from-home, paste and drop, the oEmbed preview, the face chip
   - the stage track, elapsed time, tab and favicon progress, the presenter, the
     celebration, notifications and copy/share
4. **Archive gallery**: covers US6.
5. **Clip map and strip**: covers US7. This is the only step touching the pipeline,
   because the probe-cost measurement belongs with it.
6. **Docs**: each step carries its own README and HANDOFF.md corrections in the same
   change, as the constitution requires, and step 1 carries the constitution PATCH. The
   final step is only a consistency pass.

## Complexity Tracking

No constitution violations to justify. One reversal of an earlier feature's decision is
recorded here for visibility:

| Reversal | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Hidden tabs poll every 10 s, where 002 research D2 had them stop entirely | FR-031 (tab progress) and FR-034 (notifications) are only useful while the tab is hidden | SSE: on HTTP/1.1 each tab holds one of the browser's 6 per-host connections, so the 7th tab would hang (research D10). Service-worker push: secure-context only, so unavailable on this deployment. |
