/* Shared job-progress indicator, drop-in on any page via one <script> tag.
   Injects its own markup and styles. Styled from the design tokens in
   /static/css/supercut.css (--surface, --border, --text, --muted, --accent,
   --danger, --gradient); the literal fallbacks only matter on a page that
   doesn't load the stylesheet. Exposes window.SupercutProgress. */
(function () {
  "use strict";

  const STYLE = `
    #supercut-progress {
      position: fixed; left: 0; right: 0; bottom: 0; z-index: 1000;
      background: color-mix(in oklab, var(--surface, #ffffff) 92%, transparent);
      backdrop-filter: saturate(1.4) blur(12px); -webkit-backdrop-filter: saturate(1.4) blur(12px);
      border-top: 1px solid var(--border, #e2e2eb);
      padding: 10px 16px calc(10px + env(safe-area-inset-bottom));
      box-shadow: var(--shadow-2, 0 -2px 12px rgba(0,0,0,0.08));
      font-family: var(--font, system-ui, sans-serif); color: var(--text, #15151f);
    }
    #supercut-progress.fp-hidden { display: none; }
    #supercut-progress .fp-row { display: flex; align-items: center; gap: 14px; max-width: 960px; margin: 0 auto; }
    #supercut-progress .fp-mark { width: 28px; height: 28px; border-radius: 7px; flex: none; }
    #supercut-progress .fp-body { flex: 1; min-width: 0; }
    #supercut-progress .fp-stage { font-weight: 600; font-size: 0.875rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    #supercut-progress.fp-error .fp-stage { color: var(--danger, #c8243c); }
    #supercut-progress .fp-msg { color: var(--muted, #585870); font-size: 0.75rem; margin-top: 1px;
      overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-variant-numeric: tabular-nums; }
    #supercut-progress .fp-track { height: 4px; border-radius: 999px; background: var(--raised, #efeff5);
      overflow: hidden; margin-top: 6px; }
    #supercut-progress .fp-fill { height: 100%; border-radius: 999px; background: var(--gradient, #5b3df5); }
    #supercut-progress.fp-stale .fp-fill { opacity: 0.45; }
    #supercut-progress .fp-actions { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
    #supercut-progress .fp-compact { margin-top: 6px; }
    @media (prefers-reduced-motion: no-preference) {
      #supercut-progress .fp-fill { transition: width 0.3s ease; }
    }
  `;

  const MARKUP = `
    <div class="fp-row">
      <img class="fp-mark" src="/static/brand/mark-small.svg" alt="">
      <div class="fp-body">
        <div class="fp-stage" id="fp-stage"></div>
        <div class="fp-msg" id="fp-msg"></div>
        <div class="fp-track" id="fp-track"><div class="fp-fill" id="fp-fill"></div></div>
      </div>
      <div class="fp-actions" id="fp-actions"></div>
    </div>
  `;

  const styleEl = document.createElement("style");
  styleEl.textContent = STYLE;
  document.head.appendChild(styleEl);

  const bar = document.createElement("div");
  bar.id = "supercut-progress";
  bar.className = "fp-hidden";
  bar.innerHTML = MARKUP;
  document.body.appendChild(bar);

  const stageEl = bar.querySelector("#fp-stage");
  const msgEl = bar.querySelector("#fp-msg");
  const trackEl = bar.querySelector("#fp-track");
  const fillEl = bar.querySelector("#fp-fill");
  const actionsEl = bar.querySelector("#fp-actions");

  // Bar dimensions (padding, track height) are chosen values, not derived --
  // no measurement applies to a UI element's own size (constitution Principle II).
  function showBar() {
    bar.classList.remove("fp-hidden");
    // Measured, not hard-coded, so a wrapped message on a narrow window still
    // reserves the right amount of space underneath it (research D8). Also
    // published as --bar-height, which keeps toasts and the page's last
    // control clear of the bar (004 FR-012).
    const h = bar.offsetHeight + "px";
    document.body.style.paddingBottom = h;
    document.documentElement.style.setProperty("--bar-height", h);
  }
  function hideBar() {
    bar.classList.add("fp-hidden");
    document.body.style.paddingBottom = "";
    document.documentElement.style.setProperty("--bar-height", "0px");
  }

  const STAGE_NAMES = {
    start: "Starting", reference: "Reading screenshot", download: "Downloading video",
    scan: "Scanning for the person", refine: "Refining clip boundaries",
    track: "Measuring framing", stitch: "Cutting & stitching", join: "Joining reels",
    network: "Waiting for network",
    done: "Done",
  };

  // Holds a *session* id now: the terminal notice is per session, not per
  // video, so ten videos finishing don't raise ten notices (research D9).
  //
  // There is deliberately no "watching" key any more. 002 kept the id of the
  // reel on display so it could report one that vanished in a restart. With
  // a queue, the active id changes at every normal hand-off between videos,
  // so that check would fire after every success; and a restart now
  // re-queues the video instead of losing it (FR-020), so there is nothing
  // left for it to detect. A resumed video restarting at 0% is the truthful
  // picture, not a regression (plan "Three things" #3).
  //
  // 004 research D12: the key now holds a *completion*, "<session id>@<completed_at>",
  // not just a session id. Keyed by session alone, a retry that rebuilt a
  // reel under the same id was already "acknowledged", so its "Session reel
  // ready" notice never appeared. A new completed_at is a new completion.
  const ACK_KEY = "supercut.acknowledged";
  // Pre-rename key, holding a bare session id. Read once and migrated below.
  const OLD_ACK_KEY = "facereel.acknowledged";

  function completionKey(job) {
    return job && job.kind === "session" && job.completed_at ? `${job.session_id}@${job.completed_at}` : null;
  }
  function getAcknowledged() {
    try { return localStorage.getItem(ACK_KEY); } catch { return null; }
  }
  function setAcknowledged(key) {
    try { localStorage.setItem(ACK_KEY, key); } catch { /* worst case: notice repeats once */ }
  }
  function isAcknowledged(key) { return !!key && getAcknowledged() === key; }
  // One-time migration: a notice dismissed before the upgrade must not pop
  // back up on the first load after it. The old key named the session; the
  // first terminal payload for that session becomes the acknowledged
  // completion, and the old key is removed either way once one arrives.
  function migrateOldAck(job) {
    let old;
    try { old = localStorage.getItem(OLD_ACK_KEY); } catch { return; }
    if (!old || !job || job.kind !== "session") return;
    if (old === job.id && completionKey(job)) setAcknowledged(completionKey(job));
    try { localStorage.removeItem(OLD_ACK_KEY); } catch { /* harmless */ }
  }

  const subscribers = [];
  function subscribe(callback) { subscribers.push(callback); }
  function notify(job) {
    for (const cb of subscribers) {
      try { cb(job); } catch (e) { console.error(e); }
    }
  }

  let stale = false;
  function markStale() {
    if (stale) return;
    stale = true;
    if (!bar.classList.contains("fp-hidden")) bar.classList.add("fp-stale");
  }
  function clearStale() {
    if (!stale) return;
    stale = false;
    bar.classList.remove("fp-stale");
  }

  function onSessionPage(sid) {
    return location.pathname.endsWith(`/session/${sid}`);
  }

  function sessionLink(sid, text) {
    const link = document.createElement("a");
    link.className = "btn btn-secondary btn-sm"; link.href = `/session/${sid}`; link.textContent = text;
    return link;
  }

  // FR-016: name the session and the video within it, e.g.
  // "Session 4f2a91… · video 2 of 5 · Scanning for the person".
  // The compact stage track (004 FR-029) when the shell is loaded; the plain
  // bar otherwise, and always for joins, which have a single stage.
  let compactTrack = null;
  function renderTrack(job) {
    const S = window.Supercut;
    if (!S || !S.stageTrack || job.kind === "join") {
      if (compactTrack) { compactTrack.remove(); compactTrack = null; }
      trackEl.style.display = "";
      fillEl.style.width = (job.progress || 0) + "%";
      return;
    }
    trackEl.style.display = "none";
    const args = { stage: job.stage, progress: job.progress, zoom: job.zoom, network: job.stage === "network" };
    if (!compactTrack) {
      compactTrack = S.stageTrack(args, { compact: true });
      compactTrack.classList.add("fp-compact");
      trackEl.after(compactTrack);
    } else compactTrack.update(args);
  }

  function renderProcessing(job) {
    bar.classList.remove("fp-error");
    const where = `Session ${job.session_id.slice(0, 6)}… · ` +
      (job.kind === "join" ? "joining reels" : `video ${job.index} of ${job.total} · ` +
        (STAGE_NAMES[job.stage] || "Working"));
    stageEl.textContent = where;
    // "42% · 3:05 · Scanning frame 812..." -- the elapsed time is the
    // server's own clock (004 research D11)
    const bits = [];
    if (job.stage !== "network") bits.push(`${Math.round(job.progress || 0)}%`);
    if (job.elapsed_s != null && window.Supercut) bits.push(window.Supercut.fmtDuration(job.elapsed_s));
    if (job.message) bits.push(job.message);
    msgEl.textContent = bits.join(" · ");
    renderTrack(job);
    actionsEl.innerHTML = "";
    // no link from the session's own page -- it's already showing this
    if (!onSessionPage(job.session_id)) {
      actionsEl.appendChild(sessionLink(job.session_id, "Open session"));
    }
    showBar();
  }

  function dismissButton(onClick) {
    const btn = document.createElement("button");
    btn.type = "button"; btn.className = "btn btn-quiet btn-sm"; btn.textContent = "Dismiss";
    btn.addEventListener("click", onClick);
    return btn;
  }

  function renderCompleted(job) {
    bar.classList.remove("fp-error", "fp-stale");
    trackEl.style.display = "none";
    if (compactTrack) { compactTrack.remove(); compactTrack = null; }
    stageEl.textContent = job.state === "finished" ? "Session reel ready" : "Session finished — nothing to join";
    msgEl.textContent = job.message || "Done!";
    actionsEl.innerHTML = "";
    if (!onSessionPage(job.session_id)) actionsEl.appendChild(sessionLink(job.session_id, "View session"));
    actionsEl.appendChild(dismissButton(() => { setAcknowledged(completionKey(job)); hideBar(); }));
    showBar();
  }

  function renderFailed(job) {
    bar.classList.add("fp-error");
    bar.classList.remove("fp-stale");
    trackEl.style.display = "none";
    if (compactTrack) { compactTrack.remove(); compactTrack = null; }
    stageEl.textContent = "Session reel failed";
    msgEl.textContent = job.message || "Something went wrong.";
    actionsEl.innerHTML = "";
    if (!onSessionPage(job.session_id)) actionsEl.appendChild(sessionLink(job.session_id, "View session"));
    actionsEl.appendChild(dismissButton(() => { setAcknowledged(completionKey(job)); hideBar(); }));
    showBar();
  }

  // FR-015: announce a change of stage or status, never a percentage. The
  // session page announces its own videos, so the bar stays quiet there.
  let lastSpoken = null;
  function announce(job) {
    const S = window.Supercut;
    if (!S || !S.announce || !job) { lastSpoken = null; return; }
    const sig = job.status === "processing" ? `${job.id}|${job.kind}|${job.stage}` : `${completionKey(job)}|${job.status}`;
    const first = lastSpoken === null;
    if (sig === lastSpoken) return;
    lastSpoken = sig;
    if (first || onSessionPage(job.session_id)) return;   // no announcement for what was already there
    const where = `Session ${job.session_id.slice(0, 6)}`;
    if (job.status === "processing") {
      S.announce(job.kind === "join" ? `${where}: joining reels.` :
        `${where}, video ${job.index} of ${job.total}: ${STAGE_NAMES[job.stage] || "working"}.`);
    } else if (!isAcknowledged(completionKey(job))) {
      // by state: "nothing to join" also reports status "done"
      S.announce(job.state === "finished" ? `${where}: reel ready.` :
        job.state === "nothing_to_join" ? `${where}: finished, nothing to join.` : `${where}: joining failed.`);
    }
  }

  function render(job) {
    if (!job) {
      hideBar();
      return;
    }
    if (job.status === "processing") {
      renderProcessing(job);
      return;
    }
    // Terminal: the most recently ended session. /api/jobs/active keeps
    // returning it until another session ends, so acknowledgement is what
    // stops the notice reappearing on every poll and reload (002 research
    // D5; FR-010).
    migrateOldAck(job);
    if (isAcknowledged(completionKey(job))) {
      hideBar();
      return;
    }
    if (job.status === "done") renderCompleted(job);
    else renderFailed(job);
  }

  function handleResponse(job) {
    clearStale();
    render(job);
    announce(job);
    notify(job);
  }

  let failCount = 0;
  async function poll() {
    let data;
    try {
      const res = await fetch("/api/jobs/active");
      if (!res.ok) throw new Error("bad status " + res.status);
      data = await res.json();
    } catch {
      failCount++;
      // Two, not one, so a single transient blip is not reported as an
      // outage (constitution Principle II). Keeps polling regardless --
      // the next success clears it with no reload needed (FR-015).
      if (failCount >= 2) markStale();
      return;
    }
    failCount = 0;
    handleResponse(data.job);
  }

  // 1 s while visible: already the existing rate, and half the 2-second
  // FR-004 requirement (constitution Principle II).
  //
  // 10 s while hidden. This reverses 002 research D2, which stopped hidden
  // tabs polling so that "five tabs pay five requests a second forever".
  // That held while nothing needed a hidden tab to stay current; now the tab
  // title, favicon (004 FR-031) and notifications (FR-034) are useful
  // precisely *because* the tab is hidden. Five hidden tabs at 10 s cost one
  // request every two seconds against an in-memory dict -- noise, by 002's
  // own measure. 10 s is chosen, not measured: the slowest rate at which a
  // glance at the tab still feels current. Browsers slow long-hidden tabs
  // further (Chrome: about once a minute after five minutes), whatever we
  // ask; 004 SC-008 accepts that. Server-sent events would dodge timer
  // throttling, but each tab would hold one of HTTP/1.1's six per-host
  // connections open, and the seventh tab would hang (004 research D10).
  const VISIBLE_MS = 1000, HIDDEN_MS = 10000;
  let pollTimer = null, pollEvery = 0;
  function schedule() {
    const want = document.hidden ? HIDDEN_MS : VISIBLE_MS;
    if (pollTimer && pollEvery === want) return;
    clearInterval(pollTimer);
    pollEvery = want;
    pollTimer = setInterval(poll, want);
  }
  // Becoming visible polls at once rather than waiting for the next tick, so
  // a window never shows a stale figure it could have refreshed sooner.
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) poll();
    schedule();
  });
  poll();
  schedule();

  window.SupercutProgress = { subscribe, completionKey, isAcknowledged };
})();
