// Demo videos: on a phone a tap opens one full screen (landscape for the wide one, portrait for
// the tall one, where the browser allows), so the interface can actually be read. With reduced
// motion they do not autoplay.
(() => {
  const vids = [...document.querySelectorAll(".demo-video")];
  if (!vids.length) return;
  const calmo = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const phone = matchMedia("(max-width: 640px)");
  const pt = document.documentElement.lang.toLowerCase().startsWith("pt");
  const cap = vids[0].closest("figure")?.querySelector("figcaption");
  if (cap) {
    const hint = document.createElement("span");
    hint.className = "tap-hint"; hint.textContent = pt ? "Toque num vídeo para ampliar" : "Tap a video to enlarge";
    cap.appendChild(hint);
  }
  for (const v of vids) {
    if (calmo) {
      v.removeAttribute("autoplay"); v.pause(); v.controls = true;
    }
    const lado = Number(v.getAttribute("height")) > Number(v.getAttribute("width")) ? "portrait" : "landscape";
    v.addEventListener("click", async () => {
      if (!phone.matches || document.fullscreenElement) return;
      try {
        if (v.requestFullscreen) await v.requestFullscreen();
        else if (v.webkitEnterFullscreen) { v.webkitEnterFullscreen(); return; }  // iPhone
        await screen.orientation?.lock?.(lado);
      } catch (_) { /* full screen or rotation refused: the video keeps playing in place */ }
      v.play().catch(() => {});
    });
  }
  document.addEventListener("fullscreenchange", () => {
    if (!document.fullscreenElement) screen.orientation?.unlock?.();
  });
})();
