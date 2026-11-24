// Demo videos: pause/play and fullscreen controls on desktop and phone; tapping a video opens
// it full screen (locking orientation on phones where the browser allows), so the interface can
// actually be read. With prefers-reduced-motion they start paused with native controls.
(() => {
  const vids = [...document.querySelectorAll(".demo-video")];
  if (!vids.length) return;
  const calmo = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const phone = matchMedia("(max-width: 640px)");
  const pt = document.documentElement.lang.toLowerCase().startsWith("pt");
  const txt = pt
    ? { pause: "Pausar", play: "Reproduzir", zoom: "Ampliar", hint: "Toque num vídeo para ampliar" }
    : { pause: "Pause", play: "Play", zoom: "Enlarge", hint: "Tap a video to enlarge" };

  const cap = vids[0].closest("figure")?.querySelector("figcaption");
  if (cap) {
    const hint = document.createElement("span");
    hint.className = "tap-hint";
    hint.textContent = txt.hint;
    cap.appendChild(hint);
  }

  const openFullscreen = async (v, lado) => {
    if (document.fullscreenElement) return;
    try {
      if (v.requestFullscreen) await v.requestFullscreen();
      else if (v.webkitEnterFullscreen) { v.webkitEnterFullscreen(); return; }  // iPhone
      if (phone.matches) await screen.orientation?.lock?.(lado);
    } catch (_) { /* full screen or rotation refused: the video keeps playing in place */ }
  };

  for (const v of vids) {
    if (calmo) {
      v.removeAttribute("autoplay");
      v.pause();
      v.controls = true;
    }
    const lado = Number(v.getAttribute("height")) > Number(v.getAttribute("width")) ? "portrait" : "landscape";

    // Build compact Pause/Play + Fullscreen buttons in the bar below each video.
    const bar = v.closest(".demo-item")?.querySelector(".demo-bar");
    if (bar) {
      const ctrl = document.createElement("div");
      ctrl.className = "demo-ctrl";

      const btnPlay = document.createElement("button");
      btnPlay.type = "button";
      btnPlay.className = "demo-btn";
      const syncPlay = () => {
        const paused = v.paused;
        btnPlay.textContent = paused ? "▶ " + txt.play : "⏸ " + txt.pause;
        btnPlay.setAttribute("aria-pressed", String(paused));
      };
      btnPlay.addEventListener("click", () => {
        if (v.paused) v.play().catch(() => {});
        else v.pause();
      });
      v.addEventListener("play", syncPlay);
      v.addEventListener("pause", syncPlay);
      syncPlay();

      const btnZoom = document.createElement("button");
      btnZoom.type = "button";
      btnZoom.className = "demo-btn";
      btnZoom.textContent = "⛶ " + txt.zoom;
      btnZoom.addEventListener("click", () => openFullscreen(v, lado));

      ctrl.append(btnPlay, btnZoom);
      bar.appendChild(ctrl);
    }

    v.addEventListener("click", async () => {
      if (document.fullscreenElement) return;
      await openFullscreen(v, lado);
      if (!calmo && !v.paused) v.play().catch(() => {});
    });
  }

  document.addEventListener("fullscreenchange", () => {
    if (!document.fullscreenElement) screen.orientation?.unlock?.();
  });
})();
