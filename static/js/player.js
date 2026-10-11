/* Supercut clip strip: jump between the clips inside a reel (004 FR-042,
   contracts/ui-shell.md section 5). Exposes window.SupercutPlayer.

   The video keeps the browser's native controls. Rebuilding seek, volume,
   fullscreen and picture-in-picture would be a lot of surface to get subtly
   worse, and browsers draw no chapter marks on native controls (research
   D13). So the clips are a strip of segments under the player instead.

   attach(videoEl, entry) inserts the strip after the video when entry.clips
   is a non-empty array, and nothing otherwise: a reel made before the clip
   map existed plays exactly as before (FR-043). Returns {destroy()}. */
(function () {
  "use strict";
  const S = window.Supercut;
  // Session reels are tinted by source video, cycling through six tints of
  // the brand gradient (chosen: enough to tell neighbours apart).
  const TINTS = 6;
  const MIN_SEG_PX = 3;   // so a half-second clip is still clickable

  function attach(video, entry) {
    const clips = entry && Array.isArray(entry.clips) ? entry.clips : null;
    if (!video || !clips || !clips.length) return { destroy() {} };
    const session = entry.kind === "session";
    const n = clips.length;

    const wrap = S.el("div", "clip-strip");
    wrap.setAttribute("role", "group");
    wrap.setAttribute("aria-label", `Clips: ${n}`);
    const prev = S.el("button", "btn btn-quiet btn-icon btn-sm clip-nav");
    prev.type = "button"; prev.setAttribute("aria-label", "Previous clip");
    prev.title = "Previous clip ( [ )";
    prev.appendChild(S.icon("skip-back", "icon-sm"));
    const next = S.el("button", "btn btn-quiet btn-icon btn-sm clip-nav");
    next.type = "button"; next.setAttribute("aria-label", "Next clip");
    next.title = "Next clip ( ] )";
    next.appendChild(S.icon("skip-forward", "icon-sm"));
    const track = S.el("div", "clip-track");
    const label = S.el("div", "clip-label xsmall muted tabular");
    label.setAttribute("aria-live", "polite");

    const segs = clips.map((c, i) => {
      const b = S.el("button", "clip-seg");
      b.type = "button";
      b.style.flexGrow = String(Math.max(0.001, c.end - c.start));
      b.style.minWidth = MIN_SEG_PX + "px";
      if (session && c.index) b.dataset.tint = String((c.index - 1) % TINTS);
      // a thin divider wherever the source video changes
      if (session && i > 0 && clips[i - 1].video !== c.video) b.classList.add("is-video-start");
      const at = S.fmtDuration(c.start);
      const from = session ? `, from video ${c.index}${c.title ? ": " + c.title : ""}` : "";
      const name = c.whole ? `Video ${c.index}${c.title ? ": " + c.title : ""}, ${at}` : `Clip ${i + 1} of ${n}${from}, ${at}`;
      b.setAttribute("aria-label", name);
      b.title = name;
      b.addEventListener("click", () => seekTo(i));
      track.appendChild(b);
      return b;
    });
    wrap.append(prev, track, next);
    const box = S.el("div", "clip-box");
    box.append(wrap, label);
    video.after(box);

    let current = -1;
    function indexAt(t) {
      // the last clip whose start is at or before t (small epsilon: a seek
      // lands a hair before the exact start)
      let i = 0;
      while (i + 1 < n && clips[i + 1].start <= t + 0.05) i++;
      return i;
    }
    function show(i) {
      if (i === current) return;
      if (segs[current]) segs[current].classList.remove("is-current");
      current = i;
      segs[i].classList.add("is-current");
      const c = clips[i];
      label.textContent = c.whole
        ? `Video ${c.index}${c.title ? " · " + c.title : ""}`
        : `Clip ${i + 1} of ${n}` + (session ? ` · video ${c.index}${c.title ? " · " + c.title : ""}` : "");
      prev.disabled = i <= 0 && video.currentTime - c.start < 1;
      next.disabled = i >= n - 1;
    }
    function seekTo(i) {
      i = Math.max(0, Math.min(n - 1, i));
      video.currentTime = clips[i].start + 0.01;
      show(i);
    }
    // "previous" within the first second of a clip goes to the clip before;
    // later in a clip it restarts this one, as music players do
    function goPrev() {
      const i = indexAt(video.currentTime);
      seekTo(video.currentTime - clips[i].start > 1 ? i : i - 1);
    }
    function goNext() { seekTo(indexAt(video.currentTime) + 1); }
    prev.addEventListener("click", goPrev);
    next.addEventListener("click", goNext);
    const onTime = () => show(indexAt(video.currentTime));
    video.addEventListener("timeupdate", onTime);
    video.addEventListener("seeked", onTime);
    // [ and ] only while focus is in the player or its strip, so they never
    // fight with typing elsewhere on the page
    const onKey = e => {
      if (e.key !== "[" && e.key !== "]") return;
      if (!(e.target === video || box.contains(e.target))) return;
      e.preventDefault();
      e.key === "[" ? goPrev() : goNext();
    };
    video.addEventListener("keydown", onKey);
    box.addEventListener("keydown", onKey);
    show(indexAt(video.currentTime || 0));

    return {
      destroy() {
        video.removeEventListener("timeupdate", onTime);
        video.removeEventListener("seeked", onTime);
        video.removeEventListener("keydown", onKey);
        box.remove();
      },
    };
  }

  window.SupercutPlayer = { attach };
})();
