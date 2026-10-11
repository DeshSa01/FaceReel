/* Supercut shell: what every page shares beyond the stylesheet
   (contracts/ui-shell.md section 3). Exposes window.Supercut.

   Must load BEFORE progress.js: the tab-title, favicon and notification code
   below subscribes to SupercutProgress the moment it exists, and the bar's
   restyle calls Supercut.stageTrack. Page order: shell.js, progress.js,
   [player.js], then the page's own inline script. */
(function () {
  "use strict";

  const S = {};
  window.Supercut = S;

  /* ---- page transitions (research D16) ------------------------------ */

  // Cross-document view transitions are skipped whenever they can't run (a
  // reload, a slow page, reduced motion on one side), and Chrome then rejects
  // the transition's promises. Nothing here depends on them; handle them so
  // a skipped transition isn't logged as an uncaught error.
  for (const type of ["pageswap", "pagereveal"]) {
    window.addEventListener(type, e => {
      const vt = e.viewTransition;
      if (vt) for (const p of [vt.ready, vt.finished, vt.updateCallbackDone]) p && p.catch(() => {});
    });
  }

  /* ---- core helpers ------------------------------------------------- */

  // The same el(tag, cls, text) the pages have always used.
  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  }
  S.el = el;

  const SVG_NS = "http://www.w3.org/2000/svg";
  function icon(name, cls) {
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("class", "icon" + (cls ? " " + cls : ""));
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    const use = document.createElementNS(SVG_NS, "use");
    use.setAttribute("href", `/static/icons.svg#i-${name}`);
    svg.appendChild(use);
    return svg;
  }
  S.icon = icon;

  function store(key, value) {
    // Every storage access is guarded: a private window, blocked site data or
    // a full quota throws, and the page must work regardless (spec edge case).
    try {
      if (value === undefined) return localStorage.getItem(key);
      if (value === null) localStorage.removeItem(key);
      else localStorage.setItem(key, value);
    } catch { /* fall back to defaults */ }
    return null;
  }
  S.store = store;

  /* ---- formatters (moved from the pages so they stay identical) ------ */

  S.fmtBytes = function (n) {
    if (n < 1024) return n + " B";
    const units = ["KB", "MB", "GB", "TB"];
    let v = n, i = -1;
    do { v /= 1024; i++; } while (v >= 1024 && i < units.length - 1);
    return v.toFixed(1) + " " + units[i];
  };
  S.fmtDate = function (iso) {
    return new Date(iso).toLocaleString(undefined, {
      year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    });
  };
  S.fmtShortDate = function (iso) {
    return new Date(iso).toLocaleString(undefined, {
      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    });
  };
  // 75 -> "1:15", 3725 -> "1:02:05"
  S.fmtDuration = function (s) {
    s = Math.max(0, Math.round(+s || 0));
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    const pad = n => String(n).padStart(2, "0");
    return h ? `${h}:${pad(m)}:${pad(sec)}` : `${m}:${pad(sec)}`;
  };
  S.plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

  /* ---- live region (FR-015) ------------------------------------------ */

  let live = null;
  function liveRegion() {
    if (live) return live;
    live = el("div", "visually-hidden");
    live.setAttribute("aria-live", "polite");
    live.setAttribute("role", "status");
    document.body.appendChild(live);
    return live;
  }
  // Callers announce changes of stage or state, never percentage ticks: one
  // announcement per change is what FR-015 allows.
  S.announce = function (text) {
    const r = liveRegion();
    // clearing first makes a repeat of the same sentence announce again
    r.textContent = "";
    setTimeout(() => { r.textContent = text; }, 50);
  };

  /* ---- toasts -------------------------------------------------------- */

  let stack = null;
  const TOAST_ICONS = { info: "info", success: "check", error: "alert-triangle" };
  S.toast = function (message, opts = {}) {
    const kind = opts.kind || "info";
    // 5 s is chosen, not measured: long enough to read a sentence. Errors stay
    // until dismissed, because the user may need them to decide what to do.
    const timeout = opts.timeout ?? (kind === "error" ? 0 : 5000);
    if (!stack) {
      stack = el("div", "toast-stack");
      document.body.appendChild(stack);
    }
    const t = el("div", `toast is-${kind}`);
    t.setAttribute("role", kind === "error" ? "alert" : "status");
    t.appendChild(icon(TOAST_ICONS[kind] || "info"));
    t.appendChild(el("div", "toast-msg", message));
    if (opts.action) {
      const a = el("button", "btn btn-quiet btn-sm", opts.action.label);
      a.type = "button";
      a.addEventListener("click", () => { opts.action.onClick(); close(); });
      t.appendChild(a);
    }
    const x = el("button", "btn btn-quiet btn-icon btn-sm");
    x.type = "button";
    x.setAttribute("aria-label", "Dismiss");
    x.appendChild(icon("x", "icon-sm"));
    x.addEventListener("click", close);
    t.appendChild(x);
    stack.appendChild(t);
    let timer = timeout ? setTimeout(close, timeout) : null;
    function close() {
      clearTimeout(timer);
      if (!t.isConnected) return;
      if (matchMedia("(prefers-reduced-motion: no-preference)").matches) {
        t.classList.add("is-leaving");
        setTimeout(() => t.remove(), 220);
      } else t.remove();
    }
    return { close };
  };

  /* ---- status badge (FR-009: icon + text, never colour alone) -------- */

  const BADGE_ICONS = {
    waiting: "clock", processing: "loader", done: "check", failed: "alert-triangle",
    removed: "minus", network: "wifi-off", session: "layers", joining: "loader",
  };
  S.badge = function (state, label) {
    const b = el("span", `badge is-${state === "joining" ? "processing" : state}`);
    b.appendChild(icon(BADGE_ICONS[state] || "info"));
    b.appendChild(el("span", null, label));
    return b;
  };

  /* ---- empty states (FR-014) ----------------------------------------- */

  // The illustrations are fetched and inlined rather than used as <img>,
  // because an <img> SVG resolves currentColor to black whatever the theme;
  // inline, it takes the page's --muted. Cached per name for the page's life.
  const artCache = {};
  function inlineArt(slot, name) {
    const p = artCache[name] || (artCache[name] =
      fetch(`/static/brand/empty-${name}.svg`).then(r => r.ok ? r.text() : "").catch(() => ""));
    p.then(svg => { if (svg) slot.innerHTML = svg; });
  }
  // {art: "sessions"|"archive"|"search", title, body, action: {label, onClick|href, icon}}
  S.emptyState = function ({ art, title, body, action }) {
    const box = el("div", "empty");
    if (art) {
      const slot = el("div", "empty-art");
      slot.setAttribute("aria-hidden", "true");
      inlineArt(slot, art);
      box.appendChild(slot);
    }
    box.appendChild(el("h2", null, title));
    if (body) box.appendChild(el("p", null, body));
    if (action) {
      const a = el(action.href ? "a" : "button", "btn btn-primary");
      if (action.href) a.href = action.href; else a.type = "button";
      if (action.icon) a.appendChild(icon(action.icon));
      a.appendChild(el("span", null, action.label));
      if (action.onClick) a.addEventListener("click", action.onClick);
      box.appendChild(a);
    }
    return box;
  };

  /* ---- clipboard (research D9) --------------------------------------- */

  // The clipboard API only exists on secure origins; the deployment is plain
  // HTTP on the LAN. execCommand("copy") is deprecated but still supported
  // everywhere, and is the only copy that works there. Never throws.
  S.copyText = async function (text) {
    if (window.isSecureContext && navigator.clipboard) {
      try { await navigator.clipboard.writeText(text); return true; } catch { /* fall through */ }
    }
    const ta = el("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.cssText = "position:fixed;top:0;left:0;opacity:0;pointer-events:none";
    document.body.appendChild(ta);
    const prev = document.activeElement;
    ta.select();
    let ok = false;
    try { ok = document.execCommand("copy"); } catch { ok = false; }
    ta.remove();
    if (prev && prev.focus) prev.focus({ preventScroll: true });
    return ok;
  };

  /* ---- theme (FR-016 to FR-019, research D2) ------------------------ */

  // "system" is the absence of the key. The inline script in each page's
  // <head> has already applied a stored light/dark before first paint; this
  // only handles changes. System mode needs no matchMedia listener: CSS
  // color-scheme follows the OS by itself, so don't add one.
  const THEME_KEY = "supercut.theme";
  const THEME_ICONS = { light: "sun", dark: "moon", system: "monitor" };
  const THEME_LABELS = { light: "Light", dark: "Dark", system: "System" };
  function readTheme() {
    const t = store(THEME_KEY);
    return t === "light" || t === "dark" ? t : "system";
  }
  function applyTheme(mode) {
    const root = document.documentElement;
    if (mode === "system") delete root.dataset.theme;
    else root.dataset.theme = mode;
    syncThemeControl(mode);
  }
  function syncThemeControl(mode) {
    const btn = document.getElementById("theme-btn");
    if (!btn) return;
    btn.setAttribute("aria-label", `Theme: ${THEME_LABELS[mode]}`);
    btn.title = `Theme: ${THEME_LABELS[mode]}`;
    const use = btn.querySelector("use");
    if (use) use.setAttribute("href", `/static/icons.svg#i-${THEME_ICONS[mode]}`);
    for (const item of document.querySelectorAll("[data-theme-choice]")) {
      item.setAttribute("aria-checked", String(item.dataset.themeChoice === mode));
    }
  }
  S.theme = {
    get: readTheme,
    set(mode) {
      if (!(mode in THEME_LABELS)) return;
      store(THEME_KEY, mode === "system" ? null : mode);
      applyTheme(mode);
    },
  };
  // FR-019: another tab changed it; follow without writing it back
  window.addEventListener("storage", e => {
    if (e.key === THEME_KEY || e.key === null) applyTheme(readTheme());
  });

  // The header menu: a popover, positioned under its button by hand because
  // CSS anchor positioning isn't yet in every browser this app supports.
  function initThemeControl() {
    const btn = document.getElementById("theme-btn");
    const menu = document.getElementById("theme-menu");
    if (!btn || !menu) return;
    syncThemeControl(readTheme());
    const items = [...menu.querySelectorAll("[data-theme-choice]")];
    menu.addEventListener("toggle", e => {
      if (e.newState !== "open") return;
      const r = btn.getBoundingClientRect();
      menu.style.top = `${r.bottom + 6}px`;
      menu.style.right = `${Math.max(8, innerWidth - r.right)}px`;
      menu.style.left = "auto";
      (items.find(i => i.getAttribute("aria-checked") === "true") || items[0]).focus();
    });
    for (const item of items) {
      item.addEventListener("click", () => {
        S.theme.set(item.dataset.themeChoice);
        menu.hidePopover();
        btn.focus();
      });
    }
    menu.addEventListener("keydown", e => {
      const i = items.indexOf(document.activeElement);
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        const n = items.length, next = e.key === "ArrowDown" ? (i + 1) % n : (i - 1 + n) % n;
        items[next].focus();
      } else if (e.key === "Home" || e.key === "End") {
        e.preventDefault();
        items[e.key === "Home" ? 0 : items.length - 1].focus();
      }
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initThemeControl);
  else initThemeControl();

  /* ---- YouTube links, thumbnails, face chips (FR-024 to FR-026) ------ */

  // Same rules as youtube.video_id() on the server, deliberately: the
  // preview should recognise exactly what the server would look up. A pure
  // function, so a test can be added later without restructuring (D18).
  const YT_HOSTS = new Set(["youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"]);
  const YT_ID = /^[A-Za-z0-9_-]{11}$/;
  S.youtubeId = function (url) {
    let u;
    try { u = new URL(String(url || "").trim()); } catch { return null; }
    if (u.protocol !== "http:" && u.protocol !== "https:") return null;
    const host = u.hostname.toLowerCase();
    let id = null;
    if (host === "youtu.be") id = u.pathname.slice(1).split("/")[0];
    else if (YT_HOSTS.has(host)) {
      if (u.pathname === "/watch") id = u.searchParams.get("v");
      else {
        const m = u.pathname.match(/^\/(?:shorts|live|embed|v)\/([^/]+)/);
        if (m) id = m[1];
      }
    }
    return id && YT_ID.test(id) ? id : null;
  };
  S.youtubeThumb = id => `https://i.ytimg.com/vi/${id}/mqdefault.jpg`;

  // A 16:9 thumbnail that falls back to the branded placeholder when there is
  // no YouTube id or the image fails (removed video, YouTube unreachable).
  S.thumbImg = function (url, alt = "") {
    const box = el("div", "thumb");
    const id = S.youtubeId(url);
    if (!id) { box.classList.add("is-placeholder"); return box; }
    const img = el("img");
    img.alt = alt;
    img.loading = "lazy";
    img.decoding = "async";
    img.referrerPolicy = "no-referrer";
    img.addEventListener("error", () => { img.remove(); box.classList.add("is-placeholder"); }, { once: true });
    img.src = S.youtubeThumb(id);
    box.appendChild(img);
    return box;
  };

  // The screenshot as a round "who we're looking for" chip.
  S.faceChip = function (src, label, { reused = false, compact = false } = {}) {
    const chip = el("span", "face-chip" + (reused ? " is-reused" : "") + (compact ? " is-compact" : ""));
    const ring = el("span", "face-chip-ring");
    const img = el("img");
    img.alt = "";
    img.decoding = "async";
    img.src = src;
    ring.appendChild(img);
    chip.appendChild(ring);
    if (label) chip.appendChild(el("span", "face-chip-label", label));
    return chip;
  };

  /* ---- stage track (FR-029, FR-030; data-model section 7) ------------ */

  // start and reference fold into "download" as its preparing phase: they
  // take under a second, and a stage that flashes past teaches nothing.
  const STAGES = [
    { key: "download", label: "Download", icon: "download" },
    { key: "scan", label: "Scan", icon: "scan-face" },
    { key: "refine", label: "Refine", icon: "crosshair" },
    { key: "frame", label: "Frame", icon: "crop", zoomOnly: true },
    { key: "stitch", label: "Stitch", icon: "scissors" },
  ];
  const STAGE_OF = { start: "download", reference: "download", download: "download", scan: "scan",
                     refine: "refine", track: "frame", stitch: "stitch", done: "done" };
  S.STAGE_LABELS = { download: "Downloading", scan: "Scanning", refine: "Refining", frame: "Framing",
                     stitch: "Stitching", network: "Waiting for YouTube", join: "Joining reels", done: "Done" };
  S.trackStage = stage => STAGE_OF[stage] || stage;

  // {stage, progress, elapsed_s, zoom, network, message}; returns an element
  // whose update(sameArgs) patches it in place. The clock ticks locally each
  // second and is re-synced by every update.
  S.stageTrack = function (args, { compact = false } = {}) {
    const root = el("div", "stage-track" + (compact ? " is-compact" : ""));
    const steps = el("ol", "st-steps");
    const foot = el("div", "st-foot");
    const msg = el("span", "st-msg");
    const pct = el("span", "st-pct tabular");
    const clock = el("span", "st-clock tabular");
    clock.prepend(icon("clock", "icon-sm"));
    const clockText = el("span");
    clock.appendChild(clockText);
    foot.append(msg, pct, clock);
    const bar = el("div", "st-bar"), fill = el("div", "st-fill");
    bar.appendChild(fill);
    root.append(steps, bar, foot);
    let built = null, elapsed = null, syncedAt = 0, timer = null;

    function build(zoom) {
      steps.replaceChildren();
      for (const st of STAGES) {
        if (st.zoomOnly && !zoom) continue;
        const li = el("li", "st-step");
        li.dataset.stage = st.key;
        const dot = el("span", "st-dot");
        dot.appendChild(icon(st.icon, "icon-sm"));
        li.append(dot, el("span", "st-label", st.label));
        steps.appendChild(li);
      }
      built = !!zoom;
    }
    function tick() {
      if (!root.isConnected && syncedAt && Date.now() - syncedAt > 3000) { clearInterval(timer); timer = null; return; }
      if (elapsed == null) { clock.hidden = true; return; }
      clock.hidden = false;
      clockText.textContent = S.fmtDuration(elapsed + (Date.now() - syncedAt) / 1000);
    }
    root.update = function (a) {
      if (built !== !!a.zoom) build(a.zoom);
      const network = a.network || a.stage === "network";
      // a network wait shows on the stage it interrupted, which is download
      // (the only stage that talks to YouTube)
      const cur = network ? "download" : S.trackStage(a.stage);
      const keys = [...steps.children].map(li => li.dataset.stage);
      const curIdx = cur === "done" ? keys.length : keys.indexOf(cur);
      [...steps.children].forEach((li, i) => {
        li.classList.toggle("is-done", i < curIdx);
        li.classList.toggle("is-current", i === curIdx);
        li.querySelector(".st-dot use").setAttribute("href",
          `/static/icons.svg#i-${i < curIdx ? "check" : network && i === curIdx ? "wifi-off" : STAGES.find(s => s.key === li.dataset.stage).icon}`);
      });
      root.classList.toggle("is-paused", !!network);
      const p = Math.max(0, Math.min(100, +a.progress || 0));
      fill.style.width = (network ? 100 : p) + "%";
      pct.textContent = network ? "" : `${Math.round(p)}%`;
      msg.textContent = a.message || "";
      msg.title = a.message || "";
      if (a.elapsed_s != null && !network) { elapsed = a.elapsed_s; syncedAt = Date.now(); }
      else if (network) elapsed = null;
      if (!timer) timer = setInterval(tick, 1000);
      tick();
      return root;
    };
    return root.update(args);
  };

  /* ---- tab title and favicon progress (FR-031, research D10) --------- */

  // Pages set their own title through setTitle(); this adds and removes the
  // "42% · Scanning · " prefix around it. The title is the primary signal:
  // it works in every browser. The favicon ring is an enhancement; Safari
  // does not reliably repaint a favicon changed after load.
  let baseTitle = document.title;
  let lastJob = null;
  S.setTitle = function (base) { baseTitle = base; applyTitle(); };
  function applyTitle() {
    const j = lastJob;
    if (j && j.status === "processing") {
      const stage = j.kind === "join" ? "Joining" :
        j.stage === "network" ? "Waiting for YouTube" : (S.STAGE_LABELS[S.trackStage(j.stage)] || "Working");
      const pct = j.stage === "network" ? "" : `${Math.round(j.progress || 0)}% · `;
      document.title = `${pct}${stage} · ${baseTitle}`;
    } else document.title = baseTitle;
  }

  const iconLinks = [...document.querySelectorAll('link[rel~="icon"]')];
  const originalHrefs = iconLinks.map(l => l.getAttribute("href"));
  let faviconKey = null, markImg = null;
  function loadMark() {
    if (markImg) return markImg;
    markImg = new Image();
    markImg.src = "/static/brand/favicon-32.png";
    return markImg;
  }
  function drawFavicon(j) {
    const pct = Math.round(j.progress || 0), network = j.stage === "network";
    const key = network ? "network" : `${j.kind}|${j.stage}|${pct}`;
    if (key === faviconKey) return;   // only when a whole point or the stage moves
    const img = loadMark();
    if (!img.complete || !img.naturalWidth) { img.onload = () => { faviconKey = null; drawFavicon(lastJob || j); }; return; }
    faviconKey = key;
    const c = document.createElement("canvas");
    c.width = c.height = 64;
    const g = c.getContext("2d");
    g.drawImage(img, 12, 12, 40, 40);
    g.lineWidth = 7;
    g.lineCap = "round";
    g.strokeStyle = "rgba(128,128,150,.35)";
    g.beginPath(); g.arc(32, 32, 27, 0, Math.PI * 2); g.stroke();
    const grad = g.createLinearGradient(0, 0, 64, 64);
    grad.addColorStop(0, network ? "#F5A524" : "#6A50FA");
    grad.addColorStop(1, network ? "#F5A524" : "#FF5C93");
    g.strokeStyle = grad;
    g.beginPath();
    g.arc(32, 32, 27, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * (network ? 1 : Math.max(0.02, pct / 100)));
    g.stroke();
    const url = c.toDataURL("image/png");
    for (const l of iconLinks) l.setAttribute("href", url);
  }
  function restoreFavicon() {
    if (faviconKey === null) return;
    faviconKey = null;
    iconLinks.forEach((l, i) => l.setAttribute("href", originalHrefs[i]));
  }
  function onJob(j) {
    lastJob = j;
    applyTitle();
    if (j && j.status === "processing") drawFavicon(j); else restoreFavicon();
    onJobForNotify(j);
  }

  /* ---- notifications (FR-033, FR-033a, FR-034, research D9) --------- */

  // Notifications only exist on secure origins. The deployment is plain HTTP
  // on the LAN, which isn't one -- but localhost, where development happens,
  // is. So this works on the dev machine and is absent in production unless
  // the app is put behind HTTPS. Gate on the capability, never assume it.
  const NOTIFY_KEY = "supercut.notify";
  S.notify = {
    available: () => window.isSecureContext && "Notification" in window,
    state() {
      if (!S.notify.available()) return "unavailable";
      if (Notification.permission === "denied") return "blocked";
      const answer = store(NOTIFY_KEY);
      if (answer === "declined") return "declined";
      // "accepted" is the in-page answer; the browser's own permission is
      // re-checked live, since it can be revoked in browser settings
      if (answer === "accepted") return Notification.permission === "granted" ? "accepted" : "ask";
      return "ask";
    },
    // One-time in-page offer. Permission is requested only from inside the
    // click on "Turn on", never on load (FR-033).
    offer(container) {
      if (!container) return;
      container.replaceChildren();
      const st = S.notify.state();
      if (st === "unavailable" || st === "accepted" || st === "declined") return;
      const card = el("div", "notice notify-offer");
      card.appendChild(icon("bell"));
      const body = el("div", "spacer");
      if (st === "blocked") {
        body.appendChild(el("div", null,
          "Notifications are blocked for this site. To get one when a reel is ready, allow notifications in your browser's site settings."));
        card.appendChild(body);
        const x = el("button", "btn btn-quiet btn-sm", "Dismiss");
        x.type = "button";
        x.addEventListener("click", () => { store(NOTIFY_KEY, "declined"); container.replaceChildren(); });
        card.appendChild(x);
      } else {
        body.appendChild(el("strong", null, "Get a notification when your reel is ready?"));
        body.appendChild(el("div", "xsmall muted", "Useful while this tab is in the background."));
        card.appendChild(body);
        const actions = el("div", "row-wrap");
        const yes = el("button", "btn btn-primary btn-sm", "Turn on");
        yes.type = "button";
        yes.addEventListener("click", async () => {
          let result = "denied";
          try { result = await Notification.requestPermission(); } catch { /* treated as denied */ }
          store(NOTIFY_KEY, result === "granted" ? "accepted" : "declined");
          container.replaceChildren();
          S.toast(result === "granted" ? "Notifications on. You'll hear when a reel is ready." : "Notifications stay off.",
                  { kind: result === "granted" ? "success" : "info" });
        });
        const no = el("button", "btn btn-quiet btn-sm", "Not now");
        no.type = "button";
        no.addEventListener("click", () => { store(NOTIFY_KEY, "declined"); container.replaceChildren(); });
        actions.append(yes, no);
        card.appendChild(actions);
      }
      container.appendChild(card);
    },
  };

  // Fires on the transition into a terminal payload: a completion first seen
  // while this page was alive, so opening a page after the fact never
  // notifies. The tag de-duplicates across tabs: every open tab sees the
  // same completion, the system shows one notification.
  let prevStatus = null;
  const notified = new Set();
  function onJobForNotify(j) {
    const status = j ? j.status : null;
    const wasProcessing = prevStatus === "processing";
    prevStatus = status;
    if (!j || j.kind !== "session" || !wasProcessing) return;
    const key = window.SupercutProgress && SupercutProgress.completionKey(j);
    if (!key || notified.has(key)) return;
    notified.add(key);
    if (S.notify.state() !== "accepted" || !document.hidden) return;
    try {
      // by state, not status: "nothing to join" also reports status "done"
      const heading = { finished: "Your Supercut reel is ready",
                        nothing_to_join: "Supercut: session finished, nothing to join" }[j.state] || "Supercut: joining failed";
      const n = new Notification(heading, {
        body: `Session ${j.session_id.slice(0, 6)}… · ${j.message || ""}`,
        icon: "/static/brand/icon-192.png", tag: key,
      });
      n.onclick = () => { window.focus(); location.href = `/session/${j.session_id}`; n.close(); };
    } catch { /* some platforms only allow notifications from a service worker */ }
  }

  /* ---- share (FR-035, FR-033a) ---------------------------------------- */

  S.canShare = function (url) {
    if (!navigator.share) return false;
    try { return navigator.canShare ? navigator.canShare({ url }) !== false : true; } catch { return false; }
  };
  S.share = async function ({ title, url }) {
    try { await navigator.share({ title, url }); return true; }
    catch (e) { if (e && e.name !== "AbortError") S.toast("Couldn't open the share sheet.", { kind: "error" }); return false; }
  };

  /* ---- celebration (FR-032, research D12) ----------------------------- */

  // Keys of completions already celebrated in this browser. Capped at 50
  // (chosen: far more sessions than anyone revisits) so it can't grow forever.
  const CELEBRATED_KEY = "supercut.celebrated";
  const CELEBRATED_MAX = 50;
  function celebratedList() {
    try { const v = JSON.parse(store(CELEBRATED_KEY) || "[]"); return Array.isArray(v) ? v : []; } catch { return []; }
  }
  S.celebrated = {
    has: key => celebratedList().includes(key),
    add(key) {
      const list = celebratedList().filter(k => k !== key);
      list.push(key);
      store(CELEBRATED_KEY, JSON.stringify(list.slice(-CELEBRATED_MAX)));
    },
  };

  // A short burst of gradient particles over a 400 ms spring entrance of the
  // finished reel. Under 1.6 s in all, never sound (spec assumptions). Both
  // numbers are chosen; there is nothing to measure. Under reduced motion,
  // only a fade.
  S.celebrate = function (target) {
    const reduce = !matchMedia("(prefers-reduced-motion: no-preference)").matches;
    if (target) {
      target.classList.remove("is-entering", "is-fading");
      void target.offsetWidth;
      target.classList.add(reduce ? "is-fading" : "is-entering");
    }
    if (reduce) return;
    const c = document.createElement("canvas");
    c.className = "confetti";
    c.setAttribute("aria-hidden", "true");
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    c.width = innerWidth * dpr; c.height = innerHeight * dpr;
    document.body.appendChild(c);
    const g = c.getContext("2d");
    g.scale(dpr, dpr);
    const colors = ["#6A50FA", "#8B6CFF", "#C04BD8", "#FF5C93", "#FF8FB3", "#F5A524"];
    const r = target ? target.getBoundingClientRect() : { left: innerWidth / 2, top: innerHeight / 3, width: 0 };
    const ox = r.left + r.width / 2, oy = Math.max(40, r.top + 40);
    const parts = Array.from({ length: 36 }, () => {
      const a = -Math.PI / 2 + (Math.random() - 0.5) * Math.PI * 1.1, sp = 6 + Math.random() * 7;
      return { x: ox, y: oy, vx: Math.cos(a) * sp, vy: Math.sin(a) * sp, s: 5 + Math.random() * 5,
               rot: Math.random() * 6, vr: (Math.random() - 0.5) * 0.4, c: colors[(Math.random() * colors.length) | 0],
               round: Math.random() < 0.35 };
    });
    const t0 = performance.now(), DURATION = 1600;
    (function frame(now) {
      const t = now - t0;
      g.clearRect(0, 0, innerWidth, innerHeight);
      const fade = Math.max(0, 1 - Math.max(0, t - DURATION * 0.6) / (DURATION * 0.4));
      for (const p of parts) {
        p.vy += 0.32; p.vx *= 0.985; p.x += p.vx; p.y += p.vy; p.rot += p.vr;
        g.save(); g.globalAlpha = fade; g.translate(p.x, p.y); g.rotate(p.rot); g.fillStyle = p.c;
        if (p.round) { g.beginPath(); g.arc(0, 0, p.s / 2, 0, Math.PI * 2); g.fill(); }
        else g.fillRect(-p.s / 2, -p.s / 4, p.s, p.s / 2);
        g.restore();
      }
      if (t < DURATION) requestAnimationFrame(frame); else c.remove();
    })(t0);
  };

  /* ---- wiring --------------------------------------------------------- */

  // progress.js loads after this file; by DOMContentLoaded it exists.
  function wireProgress() {
    if (window.SupercutProgress) SupercutProgress.subscribe(onJob);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", wireProgress);
  else setTimeout(wireProgress, 0);
})();
