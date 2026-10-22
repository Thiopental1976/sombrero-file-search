// Demo video: on a phone a tap opens it full screen (landscape where the browser allows),
// so the interface can actually be read. With reduced motion it does not autoplay.
(() => {
  const v = document.querySelector(".demo-video");
  if (!v) return;
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) {
    v.removeAttribute("autoplay"); v.pause(); v.controls = true;
  }
  const phone = matchMedia("(max-width: 640px)");
  const pt = document.documentElement.lang.toLowerCase().startsWith("pt");
  const cap = v.closest("figure")?.querySelector("figcaption");
  if (cap) {
    const hint = document.createElement("span");
    hint.className = "tap-hint"; hint.textContent = pt ? "Toque no vídeo para ampliar" : "Tap the video to enlarge";
    cap.appendChild(hint);
  }
  v.addEventListener("click", async () => {
    if (!phone.matches || document.fullscreenElement) return;
    try {
      if (v.requestFullscreen) await v.requestFullscreen();
      else if (v.webkitEnterFullscreen) { v.webkitEnterFullscreen(); return; }  // iPhone
      await screen.orientation?.lock?.("landscape");
    } catch (_) { /* full screen or rotation refused: the video keeps playing in place */ }
    v.play().catch(() => {});
  });
  document.addEventListener("fullscreenchange", () => {
    if (!document.fullscreenElement) screen.orientation?.unlock?.();
  });
})();
