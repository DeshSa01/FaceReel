# Phase 0 Research: Persistent Job Progress

No `NEEDS CLARIFICATION` markers reached this phase. The spec's three candidate ambiguities were settled in its Assumptions before planning began. What follows is the design reasoning and the alternatives rejected.

One finding shapes the whole plan and is worth stating first: **the server side of the user's request already works.** `_worker` in `app.py` runs on a daemon thread that never consults the client, so closing the browser has never interrupted a reel. What is missing is entirely on the client: the job id lives only in a closure variable inside `index.html`'s `poll(id)`, so once that page unloads nothing in the world can find the job again. This feature is therefore about *discovery and presentation*, not about background execution — which is why `pipeline.py` is untouched and `app.py` gains one endpoint rather than a job manager.

## D1. How a freshly loaded page finds the reel being processed

**Decision**: A new endpoint, `GET /api/jobs/active`, that reports the reel currently being processed — or, if none is, the most recently finished one. The client sends nothing and remembers nothing in order to ask.

**Rationale**: FR-002 requires discovery "without that page supplying an identifier it remembered from a previous visit", and that requirement is doing real work: an id in `localStorage` would be absent in a different browser, on a second device, and in a private window, and would be wrong after the user clears site data. Because the application processes at most one reel at a time (spec Assumptions), "the active reel" is a well-defined singleton the server can name on its own. Every window therefore converges on the same answer, which is what FR-013 asks for, and it converges without any cross-window coordination.

Returning the most recent *finished* reel from the same endpoint — rather than only an in-flight one — is what makes FR-008 and FR-009 reachable. If the endpoint went silent the instant a reel completed, a user on the archive page would see the indicator vanish with no idea whether the reel succeeded or died.

**Alternatives rejected**:
- *Client-side `localStorage` job id.* Fails the fresh-browser and second-device cases outright, and can go stale in a way the client cannot detect. It survives only as a narrow supporting role in D4.
- *A URL parameter carrying the job id across navigation.* Breaks the moment the user closes the window, types the address by hand, or follows a bookmark — the exact scenarios the feature exists for.
- *Listing all jobs and letting the client pick.* More surface, no more capability, and it would expose the unbounded in-memory `jobs` dict to the client.

## D2. Polling, not server-sent events or websockets

**Decision**: Keep HTTP polling. One request per second while the page is visible; none at all while it is hidden, with an immediate catch-up request when it becomes visible again.

**Rationale**:
- FR-004 asks for a change to be reflected within 2 seconds. A 1-second poll meets that with margin, and the existing code already polls at exactly this rate, so the cadence is not a new risk.
- Reconnection is free. FR-015 requires live updates to resume by themselves after the application becomes reachable again; with polling, the next request simply succeeds. An event stream would need explicit reconnect-and-backoff logic, which is more code to get right in exchange for latency nobody asked for.
- Principle IV (*Earn Every Dependency*): polling adds nothing. Server-sent events would need no new package either, but they hold an open connection per tab against a single-worker uvicorn on a four-core box that is already saturated by ffmpeg during precisely the period the connection is held.

Suspending the poll on `visibilitychange` matters more than it looks: without it, a user who leaves five tabs open pays five requests a second forever. With it, a hidden tab costs nothing, and because it polls immediately on becoming visible, the user never actually *sees* a stale figure.

**Cost accepted**: a visible idle page polls once a second even when nothing is happening. This is what lets a window notice a reel started in another window (FR-013) within the FR-004 interval. The response is a few hundred bytes and the handler reads an in-memory dict; against a machine encoding video, it is noise.

**Alternatives rejected**:
- *Server-sent events.* Rejected on the open-connection cost above, not on capability. Reconsider if progress ever needs sub-second granularity.
- *Websockets.* Everything wrong with SSE here, plus a protocol upgrade and a dependency, for a strictly one-way stream of small updates.
- *Slower polling when idle (3–5s).* Would weaken the FR-013 guarantee for a window that was idle when another window started a reel, in exchange for saving requests that cost nothing.

## D3. One shared asset, injected into both pages

**Decision**: A single new file, `static/progress.js`, served by an explicit route with `Cache-Control: no-cache`. It injects its own markup *and* its own styles into whatever page loads it. Both `index.html` and `archive.html` include it with one `<script>` tag.

**Rationale**: The two pages today are independent documents with separately maintained copies of the same `:root` variables and body rules. Duplicating an indicator — markup, CSS, poll loop, reconnect handling, acknowledgement logic — into both would create exactly the kind of divergence that leaves one page fixed and the other quietly broken. A behaviour required to be identical on *every* page (FR-003) should exist once.

Injecting the CSS from the same file, rather than adding a second `progress.css` route, keeps it to one asset and one round trip, and makes the component genuinely drop-in: adding it to any future page is one script tag. The injected rules consume the existing `--card`, `--border`, `--accent`, `--muted` and `--text` variables with literal fallbacks, so the bar still renders correctly on a page that has not defined them.

**On the cache header** — this is not incidental. `index.html` already carries a comment explaining that `FileResponse` sends no `Cache-Control`, so browsers heuristically cache and serve a stale copy across restarts. A shared script is *more* exposed to this than the pages are, because a stale `progress.js` against a current `app.py` produces a bar that silently stops working after a redeploy. Serving it through an explicit route that sets `no-cache`, exactly as `/` and `/archive` already do, keeps one rule for all served assets.

**Alternatives rejected**:
- *Duplicate the code in both HTML files.* Rejected on drift. Two copies of a poll loop is the specific thing that rots.
- *`app.mount("/static", StaticFiles(...))`.* Starlette is already a pinned dependency so this adds no package, but `StaticFiles` sets its own validators rather than `no-cache`, which reintroduces the staleness problem the existing routes were written to avoid. A mount also exposes the whole directory, where the current code exposes named files deliberately.
- *A shared HTML partial assembled server-side.* Would mean a template engine — a new dependency and a build-ish step — for two pages.

## D4. Reporting a reel that was interrupted

**Decision**: The client keeps, in `localStorage`, the id of the reel it is currently *displaying as in progress*. It uses this for one purpose only: to notice that a reel it was watching has vanished from the server's answer, and to say so.

**Rationale**: FR-012 exists because a redeploy is routine here — CI publishes an image on every push to `main` — and job state is an in-memory dict wiped with the process. Without this, a user watching a reel through a redeploy would see the indicator simply disappear, and would reasonably assume the reel finished. With it, the bar says the reel did not finish. Spec Assumptions put resuming out of scope; honest reporting is what remains, and a silently vanishing bar is the failure this requirement names.

This does not contradict D1 or FR-002. The remembered id is never used to *find* a reel — discovery is always the server's answer to `GET /api/jobs/active`. It is used only to detect a disappearance, a thing the server by definition cannot report, because after a restart it has no memory that the reel ever existed.

**Alternatives rejected**:
- *Persist job records to disk so they survive a restart.* Would make the interruption reportable from the server, but a persisted record of a reel whose worker thread is gone is a record of a reel that will never progress — so it needs a "was interrupted" sweep at start-up anyway. Larger change, same user-visible outcome.
- *Say nothing and hide the bar.* Directly violates FR-012, and is the current behaviour's failure mode.

## D5. Acknowledging a finished reel

**Decision**: The id of the last acknowledged reel is stored in `localStorage`, per browser. A terminal reel whose id matches is not displayed.

**Rationale**: FR-010 requires a completion notice to be dismissible and to stay dismissed. Because `GET /api/jobs/active` keeps returning the most recent finished reel until a new one starts (D1), something must remember that the user has already been told, or the bar would return on every page load until the next reel. Acknowledgement is a per-browser display preference with no meaning on the server and no consequence if it is lost — the worst case is being shown a completion notice a second time. That makes `localStorage` the right home for it, and it is the only piece of state here that legitimately belongs on the client.

**Alternatives rejected**:
- *Server-side acknowledgement flag.* Makes a display preference into shared state; a second window acknowledging would clear the notice a user in the first window had not yet read.
- *Auto-hide after a timeout.* Guarantees the notice is missed by exactly the user this feature is for — the one who walked away.

## D6. A latent crash in the existing job snapshot, which this feature would make routine

**Decision**: Seed `output_path` (and every other key the worker sets) in the job record at creation, so the worker only ever *replaces* values and never *adds* a key.

**Rationale**: `create_job` builds the record with seven keys; `_worker` later calls `job.update(..., output_path=...)`, which adds an eighth. Meanwhile `get_job` builds its response by iterating `job.items()`. A dict that gains a key during iteration raises `RuntimeError: dictionary changed size during iteration`. Today the window is a few microseconds once per job, hit only if a poll lands exactly as the job completes — rare enough to have never been seen. This feature polls from every page, all the time, including at the moment of completion, which is precisely when the extra key appears.

Seeding the key at creation removes the failure rather than narrowing it: with the record's shape fixed for its lifetime, a concurrent `update()` can only replace values, and reading it is safe under the GIL without any locking. Guarding the read with `jobs_lock` instead would *not* fix it — the worker does not hold that lock when it updates a job.

Per Principle I this needs a comment at the seeding site, because a future reader will find a `None` that is never read and be tempted to delete it.

**Alternatives rejected**:
- *Take `jobs_lock` around the snapshot.* Does not work; the writer does not take it. Making the worker take it on every progress callback adds contention on the pipeline's hot path for no benefit.
- *`copy.deepcopy` / `dict(job)`.* `dict(job)` iterates too. Same exposure.

## D7. Route ordering for `/api/jobs/active`

**Decision**: Declare `GET /api/jobs/active` immediately above `GET /api/jobs/{job_id}`, with a comment stating what breaks if they are reordered.

**Rationale**: FastAPI matches routes in declaration order. Declared after the parameterised route, `active` would be captured as a `job_id`, and the endpoint would answer `404` forever — a silent failure in which the indicator simply never appears. Job ids are `^[0-9a-f]{12}$`, so `active` can never collide with a real id; only the ordering matters.

Keeping the path under `/api/jobs/` is worth this small fragility, because it keeps the API surface coherent with `/api/jobs/{id}` and `/api/archive/{id}`. Principle I's answer to a load-bearing ordering decision is to comment it, which is cheaper than contorting the URL to dodge it.

**Alternative rejected**: *`/api/active-job`, sidestepping ordering entirely.* Defensible, and genuinely immune to a careless reorder. Rejected because it fragments the API's shape to avoid a hazard that one comment and one adjacent declaration handle.

## D8. Not covering the page beneath it

**Decision**: The bar is `position: fixed` at the bottom. While it is shown, the script sets `document.body.style.paddingBottom` to the bar's measured height, and clears it when the bar hides.

**Rationale**: FR-016 requires that nothing on a page becomes unreachable. A fixed bar over the archive grid would otherwise sit on top of the last row of reels — permanently, since the page cannot scroll past its own end. Measuring the rendered height rather than hard-coding it keeps the reservation correct when the bar's content wraps on a narrow window, which is the case where a guessed constant would be wrong.

Both pages set `body { display: flex; padding: 40px 16px }`. Padding is composable with that, and a fixed-position element is out of flow, so nothing about the existing centring changes.

**Alternative rejected**: *A sticky bar inside the page flow.* Both pages centre a `main` of bounded width inside a flex body; a full-bleed sticky element would have to be restructured into that layout on each page separately, which is the duplication D3 exists to avoid.

## D9. Getting from the notice to the finished reel

**Decision**: The completion notice links to `/archive#<id>`, and `archive.html` opens that reel's player when it loads with a matching hash (or when the hash changes while it is already open).

**Rationale**: The archive entry id *is* the job id — `archive_job(job_id, ...)` writes `"id": job_id` and builds `entry_dir(job_id)`. So the id the indicator is already holding addresses the archived reel directly, with nothing new to plumb through. FR-008 asks for a way to reach the finished reel from whichever page the user is on, and this is one link that works from both, including when the user is already on the archive page.

Handling `hashchange`, not just load, is what makes it work in the case it is most needed: the user is *on* the archive page when the reel finishes, and a link that only acted on page load would appear to do nothing.

**Alternative rejected**: *Navigate automatically on completion.* Rejected in the spec's checklist reasoning and restated here: taking over navigation while the user is watching a video is a regression, not a convenience.

## D10. Retiring `index.html`'s private poller

**Decision**: Delete `poll(id)` and `finish()` from `index.html`. The generator's progress card, submit-button state, and result card all become reactions to the shared tracker's updates.

**Rationale**: Two independent pollers for one job would double the request rate and, worse, disagree — one could show a completion the other had not yet seen. FR-013 requires a single answer. Keeping the shared tracker as the sole source also means the generator page inherits reconnection (FR-015), interruption reporting (FR-012), and the disabled submit button (FR-014) rather than reimplementing them.

The generator page keeps its own presentation: the in-page progress card and the result card with its stats line and download link stay exactly as they are (spec Assumptions), now driven by callbacks instead of by their own timer.

**Alternative rejected**: *Leave the existing poller and add the bar alongside it.* Two timers, two truths, double the requests.

## D11. Telling stale from live

**Decision**: After two consecutive failed requests the bar marks itself as showing a last-known figure and says contact was lost. It keeps polling; the first success clears the state and resumes normal display.

**Rationale**: FR-015 requires both halves — that staleness is visible, and that recovery needs no reload. Two failures rather than one avoids flagging every transient blip as an outage, at the cost of two seconds of delay in a state that is itself informational. A bar that keeps showing 47% during an outage, with no indication, is indistinguishable from a stalled reel; that ambiguity is what the requirement removes.
