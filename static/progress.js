/* Shared job-progress indicator, drop-in on any page via one <script> tag.
   Injects its own markup and styles; requires nothing from the host page
   beyond the --card/--border/--accent/--muted/--text variables both pages
   already define (literal fallbacks below cover a page that doesn't). */
(function () {
  "use strict";

  const STYLE = `
    #facereel-progress {
      position: fixed; left: 0; right: 0; bottom: 0; z-index: 1000;
      background: var(--card, #ffffff); border-top: 1px solid var(--border, #e2e8f0);
      padding: 12px 16px; box-shadow: 0 -2px 12px rgba(0,0,0,0.08);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      color: var(--text, #1a2130);
    }
    #facereel-progress.fp-hidden { display: none; }
    #facereel-progress .fp-row { display: flex; align-items: center; gap: 12px; max-width: 640px; margin: 0 auto; }
    #facereel-progress .fp-body { flex: 1; min-width: 0; }
    #facereel-progress .fp-stage { font-weight: 600; font-size: 0.9rem; }
    #facereel-progress.fp-error .fp-stage { color: var(--error, #dc2626); }
    #facereel-progress .fp-msg { color: var(--muted, #64748b); font-size: 0.8rem; margin-top: 2px;
      overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    #facereel-progress .fp-track { height: 6px; border-radius: 3px; background: var(--border, #e2e8f0);
      overflow: hidden; margin-top: 6px; }
    #facereel-progress .fp-fill { height: 100%; background: var(--accent, #4f46e5); transition: width 0.3s; }
    #facereel-progress.fp-stale .fp-fill { opacity: 0.5; }
    #facereel-progress .fp-actions { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
    #facereel-progress a.fp-link { color: var(--accent, #4f46e5); font-size: 0.85rem; text-decoration: none; font-weight: 600; }
    #facereel-progress a.fp-link:hover { text-decoration: underline; }
    #facereel-progress button.fp-dismiss {
      background: none; border: 1px solid var(--border, #e2e8f0); color: var(--muted, #64748b);
      border-radius: 6px; padding: 4px 10px; font-size: 0.8rem; cursor: pointer; font: inherit;
    }
  `;

  const MARKUP = `
    <div class="fp-row">
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
  bar.id = "facereel-progress";
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
    // reserves the right amount of space underneath it (research D8).
    document.body.style.paddingBottom = bar.offsetHeight + "px";
  }
  function hideBar() {
    bar.classList.add("fp-hidden");
    document.body.style.paddingBottom = "";
  }

  const STAGE_NAMES = {
    start: "Starting", reference: "Reading screenshot", download: "Downloading video",
    scan: "Scanning for the person", refine: "Refining clip boundaries",
    track: "Measuring framing", stitch: "Cutting & stitching", done: "Done",
  };

  const WATCH_KEY = "facereel.watching";
  const ACK_KEY = "facereel.acknowledged";

  function getWatching() {
    try { return localStorage.getItem(WATCH_KEY); } catch { return null; }
  }
  function setWatching(id) {
    try {
      if (id) localStorage.setItem(WATCH_KEY, id);
      else localStorage.removeItem(WATCH_KEY);
    } catch { /* localStorage unavailable -- display state, safe to lose */ }
  }
  function getAcknowledged() {
    try { return localStorage.getItem(ACK_KEY); } catch { return null; }
  }
  function setAcknowledged(id) {
    try { localStorage.setItem(ACK_KEY, id); } catch { /* worst case: notice repeats once */ }
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

  function renderProcessing(job) {
    bar.classList.remove("fp-error");
    trackEl.style.display = "";
    stageEl.textContent = STAGE_NAMES[job.stage] || "Working";
    msgEl.textContent = job.message || "";
    fillEl.style.width = (job.progress || 0) + "%";
    actionsEl.innerHTML = "";
    showBar();
  }

  function renderInterrupted() {
    bar.classList.remove("fp-error", "fp-stale");
    trackEl.style.display = "none";
    stageEl.textContent = "Reel did not finish";
    msgEl.textContent = "The application restarted before this reel completed.";
    actionsEl.innerHTML = "";
    const dismiss = document.createElement("button");
    dismiss.type = "button"; dismiss.className = "fp-dismiss"; dismiss.textContent = "Dismiss";
    dismiss.addEventListener("click", hideBar);
    actionsEl.appendChild(dismiss);
    showBar();
  }

  function dismissButton(onClick) {
    const btn = document.createElement("button");
    btn.type = "button"; btn.className = "fp-dismiss"; btn.textContent = "Dismiss";
    btn.addEventListener("click", onClick);
    return btn;
  }

  function renderCompleted(job) {
    bar.classList.remove("fp-error", "fp-stale");
    trackEl.style.display = "none";
    stageEl.textContent = "Reel finished";
    msgEl.textContent = job.message || "Done!";
    actionsEl.innerHTML = "";
    const link = document.createElement("a");
    link.className = "fp-link"; link.href = `/archive#${job.id}`; link.textContent = "View reel";
    actionsEl.appendChild(link);
    actionsEl.appendChild(dismissButton(() => { setAcknowledged(job.id); hideBar(); }));
    showBar();
  }

  function renderFailed(job) {
    bar.classList.add("fp-error");
    bar.classList.remove("fp-stale");
    trackEl.style.display = "none";
    stageEl.textContent = "Reel failed";
    msgEl.textContent = job.message || "Something went wrong.";
    actionsEl.innerHTML = "";
    actionsEl.appendChild(dismissButton(() => { setAcknowledged(job.id); hideBar(); }));
    showBar();
  }

  function render(job) {
    if (!job) {
      setWatching(null);
      hideBar();
      return;
    }
    if (job.status === "processing") {
      setWatching(job.id);
      renderProcessing(job);
      return;
    }
    // Terminal (done/error). /api/jobs/active keeps returning this record
    // until a new job replaces it, so acknowledgement is what stops the
    // notice from reappearing on every subsequent poll and reload (research
    // D5; FR-010).
    setWatching(null);
    if (getAcknowledged() === job.id) {
      hideBar();
      return;
    }
    if (job.status === "done") renderCompleted(job);
    else renderFailed(job);
  }

  function handleResponse(job) {
    clearStale();
    const watching = getWatching();
    if (watching && (!job || job.id !== watching)) {
      // The reel this browser was displaying as processing is no longer in
      // the server's answer at all -- the only way a restart-interrupted
      // reel is detectable, since the record itself died with the process
      // (research D4). A job that merely finished keeps the same id, so
      // this never fires for a normal completion.
      setWatching(null);
      renderInterrupted();
      notify(null);
      return;
    }
    render(job);
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

  let pollTimer = null;
  function startPolling() {
    if (pollTimer) return;
    poll();
    // Already the existing rate, and half the 2-second FR-004 requirement
    // (constitution Principle II).
    pollTimer = setInterval(poll, 1000);
  }
  function stopPolling() {
    clearInterval(pollTimer);
    pollTimer = null;
  }

  // Hidden tabs poll not at all; becoming visible polls immediately rather
  // than waiting for the next tick, so a window never shows a stale figure
  // it could have refreshed sooner (research D2; FR-004, FR-013).
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stopPolling();
    else startPolling();
  });
  if (!document.hidden) startPolling();

  window.FaceReelProgress = { subscribe };
})();
