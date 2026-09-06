# Implementation Plan: Persistent Job Progress

**Branch**: `002-persistent-job-progress` | **Date**: 2026-09-06 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-persistent-job-progress/spec.md`

## Summary

Let a user do something else while a reel is being made, and never lose track of it.

The starting point is better than it looks: `_worker` already runs on a daemon thread that never consults the client, so **processing has always survived the browser closing**. What has never survived is the *knowledge* of it — the job id lives in a closure inside `index.html`'s `poll(id)`, so unloading that page destroys the only handle anyone had on the reel.

The approach follows from that. The application becomes the authority on what is being processed, and every page asks it:

- **One new endpoint, `GET /api/jobs/active`**, naming the reel currently being processed — or the most recently finished one. The client sends nothing and remembers nothing to ask. Because at most one reel exists at a time, this is a well-defined singleton, and every window converges on the same answer without any cross-window coordination.
- **One new shared asset, `static/progress.js`**, that injects its own markup and styles into any page that includes it, polls that endpoint, and renders the bottom bar. Written once, included by both pages, so the behaviour FR-003 requires on *every* page cannot drift between them.
- **`index.html`'s private poller is deleted.** Its progress card, submit button and result card become reactions to the shared tracker, so there is one timer and one truth.

`pipeline.py` and `archive.py` are untouched. Three decisions carry most of the design:

- **Discovery is server-side; only display state is client-side.** The client holds two `localStorage` values — the reel it is watching, and the last reel it acknowledged — and neither is ever used to *find* a reel. The first exists solely to notice that a reel has vanished from the server's answer, which is the only way an interrupted reel can be reported at all (FR-012); the second so a completion notice stays dismissed (FR-010).
- **Polling, not an event stream.** It meets the 2-second requirement with margin, reconnects for free — which is most of FR-015 — and holds no open connection against a single-worker uvicorn on a four-core box during exactly the minutes it is busiest encoding.
- **A latent crash gets fixed on the way past.** `_worker` adds an `output_path` key that `get_job` can be iterating over, which raises `RuntimeError` if a poll lands as a job completes. Rare today; routine once every page polls continuously. Seeding the key at creation fixes it by making the record's shape constant for its lifetime.

## Technical Context

**Language/Version**: Python 3.14 (container and dev venv both) plus plain browser JavaScript. No transpiler, bundler, or framework — consistent with the existing two hand-written pages.

**Primary Dependencies**: FastAPI + uvicorn (existing). **No new Python packages, and no JavaScript packages at all.** No new system binaries.

**Storage**: None added. The active-reel record is the existing in-memory `jobs` dict. Two small `localStorage` keys hold per-browser display state, which is disposable by design — losing it costs at worst one repeated completion notice.

**Testing**: The repository has no test suite and this feature does not add one (constitution, *Development Workflow*). Verification is the manual script in `quickstart.md`, which is written around the two things that cannot be checked by reading code: a real browser close mid-reel, and a container redeploy mid-reel.

**Target Platform**: Linux container (`ghcr.io/deshsa01/facereel`) on an Intel N95 home server; also runs directly on macOS for development. Browser side targets current Chrome, Safari and Firefox — `visibilitychange`, `localStorage` and `fetch` only, all long-standard.

**Project Type**: Single small web service — a Python backend serving static HTML pages. No build step.

**Performance Goals**: Progress reflected within 2 seconds of changing (FR-004). One request per second per *visible* page; hidden tabs poll not at all. Each response is a few hundred bytes served from an in-memory dict.

**Constraints**: Single instance, single worker — the one-reel-at-a-time rule is what makes "the active reel" a singleton the server can name, so the feature depends on that constraint rather than merely tolerating it. The added request load lands on a machine already saturated by ffmpeg during precisely the period the polling happens. The indicator must not cover page content (FR-016). Nothing may be introduced that requires the browser to stay open.

**Scale/Scope**: One user, a handful of open tabs at most, one reel at a time, trusted home network. No accounts, no per-user scoping, no queue.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Checked against **FaceReel Constitution v1.0.0** (ratified 2026-09-05).

| Principle | Verdict | Evidence in this plan |
|---|---|---|
| I. Explain Why, Not What | **PASS** | Three comments are required by name, not left to taste: why `output_path` is seeded to `None` and never read (D6 — a future reader will otherwise delete it), why `/api/jobs/active` must be declared above `/api/jobs/{job_id}` (D7 — reordering breaks it silently), and why `progress.js` is served with `no-cache` (D3 — a stale copy against a current `app.py` produces a bar that quietly stops working after a redeploy). |
| II. Measure Before Tuning | **PASS (narrow)** | No threshold affecting reel quality is introduced. See the note below on the three arbitrary numbers. |
| III. Verify In The Environment That Ships | **PASS** | `quickstart.md` separates local from container steps. Its two decisive steps — closing the browser entirely mid-reel, and redeploying the container mid-reel — cannot be established by reading code, and the redeploy step is the one that exercises FR-012 as it will actually be hit in production. |
| IV. Earn Every Dependency | **PASS** | Zero new packages of any kind. `StaticFiles` was available at no dependency cost and was still rejected (D3) on cache-header behaviour, not on weight. |
| V. Destructive Operations Are Explicit And Bounded | **PASS (not engaged)** | The feature deletes nothing and writes no files. It builds no filesystem paths, so no id reaches one. The only id used for addressing is in a `/archive#<id>` fragment, consumed by the existing archive page whose endpoints already validate against `^[0-9a-f]{12}$`. |

**Runtime & Deployment Constraints:**

- *Single instance, single worker* — **relied upon, and stated as the constitution requires.** "The active reel" is a singleton only because the process enforces one reel at a time in memory. Under a second worker, `GET /api/jobs/active` would answer from whichever process took the request and would be wrong roughly half the time. This is not a new constraint — the same is already true of `POST /api/jobs`'s 409 check and `GET /api/jobs/{id}` — but this feature makes the whole UI depend on it, so it is recorded here and in the contract.
- *Durable data lives under `storage/`* — the feature writes nothing to disk at all. Reels stay durable through the existing archive.
- *The host is modest* — the added load is one small in-memory read per second per visible tab, against a machine running ffmpeg. Hidden tabs are suspended specifically so idle windows cost nothing (D2).
- *The image is built by CI* — a redeploy mid-reel kills the reel, which is why FR-012 exists and why the container redeploy is a required verification step rather than an optional one.
- *Documentation must not outlive its truth* — the README currently describes progress as something watched on the generator page, and `HANDOFF.md` §7 lists "Jobs are in-memory: restarting uvicorn loses job history" among the limitations. The first becomes wrong with this feature; the second stays true but acquires a user-visible consequence that must be written down. Both are corrected in the same change.

**Note on Principle II.** Three arbitrary numbers are introduced: the 1-second poll interval, the two-failure threshold before declaring staleness, and the bar's own dimensions. None affects reel quality — the principle's subject — and none is measurable in any meaningful sense. Per the principle's intent they MUST be commented as chosen values with their reasoning (the poll interval as "already the existing rate, and half the 2s requirement"; the failure threshold as "two, so a single transient blip is not reported as an outage"), rather than presented as derived. The failure mode the principle guards against is a guessed number that later reads as authoritative.

## Project Structure

### Documentation (this feature)

```text
specs/002-persistent-job-progress/
├── plan.md              # This file
├── research.md          # Phase 0 output — D1..D11
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── active-job-api.md
├── checklists/
│   └── requirements.md  # from /speckit-specify
└── tasks.md             # Phase 2 — NOT created by /speckit-plan
```

### Source Code (repository root)

```text
app.py                   # + GET /api/jobs/active, + GET /static/progress.js route,
                         #   seed output_path at creation (D6)
static/
├── progress.js          # NEW — the shared indicator: markup, styles, poll loop,
                         #   reconnect, acknowledgement. Included by both pages.
├── index.html           # + <script src="/static/progress.js">; delete poll()/finish();
                         #   progress card, submit button and result card become
                         #   reactions to the shared tracker
└── archive.html         # + <script src="/static/progress.js">; open a reel when
                         #   loaded with #<id>, and on hashchange (D9)

pipeline.py              # untouched
archive.py               # untouched
README.md                # progress/navigation behaviour corrected
HANDOFF.md               # §7 limitation restated, new feature recorded
```

**Structure Decision**: The existing flat layout is kept — `app.py` plus one module per concern, `static/` for pages. This feature adds no module because it adds no domain logic: the server change is one read-only endpoint over state that already exists, and everything genuinely new is presentation, which belongs in `static/`. `progress.js` is the one new file, and it exists as a file rather than as markup in two pages specifically so that a behaviour required to be identical everywhere has exactly one implementation.

## Post-Design Constitution Re-Check

*Re-evaluated after Phase 1. Verdicts unchanged; the design produced two things worth recording.*

| Principle | Verdict | What Phase 1 changed |
|---|---|---|
| I. Explain Why, Not What | **PASS** | Unchanged. The three required comments are now pinned to named sites in `contracts/active-job-api.md` and `data-model.md`, so `/speckit-tasks` can turn each into a task rather than leaving it to reviewer memory. |
| II. Measure Before Tuning | **PASS (narrow)** | Unchanged. No fourth arbitrary number appeared during design. |
| III. Verify In The Environment That Ships | **PASS** | Strengthened. `quickstart.md` step 12 redeploys the container *mid-reel*, which is the literal production event FR-012 exists for — a local Ctrl-C (step 8) proves the logic but not the deployment. Step 11 checks the `no-cache` header on the new asset, a failure that would only ever appear after a deploy. |
| IV. Earn Every Dependency | **PASS** | Unchanged. Still zero new packages. |
| V. Destructive Operations Are Explicit And Bounded | **PASS (not engaged)** | Unchanged. Design confirmed no id from this feature reaches a filesystem path; the `/archive#<id>` fragment is consumed by existing endpoints that already validate it. |

**Two things Phase 1 surfaced:**

1. **Part of the spec is already satisfied.** FR-001 (processing survives the browser closing) and FR-017 (reels that finish unattended are in the archive) are both true today — the first because `_worker` is a detached daemon thread, the second because feature 001 archives independently of any session. The contract marks them *verified, not built*. This matters for honest scoping: the user asked for server-side continuation and it exists; what was actually missing was the client's ability to find the reel again. Tasks for these two should be verification steps, not implementation.

2. **A pre-existing bug is in scope now.** Research D6 found that `get_job` can raise `RuntimeError` when polled at the exact moment a reel completes, because `_worker` adds a key mid-iteration. This is not a defect introduced here, but this feature turns a rare race into a routine one by polling continuously from every page. Fixing it is one seeded field; `quickstart.md` step 10 drives it deliberately rather than trusting that it cannot happen.

## Complexity Tracking

> No Constitution Check violations. This section is intentionally empty.
