// Demo videos: orientation tabs (Landscape on desktop, Portrait on phone), pause/play and
// fullscreen controls with a lightbox fallback when the browser blocks fullscreen.
// With prefers-reduced-motion they start paused with native controls.
(() => {
  const vids = [...document.querySelectorAll(".demo-video")];
  if (!vids.length) return;
  const calmo = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const phone = matchMedia("(max-width: 640px)");
  const pt = document.documentElement.lang.toLowerCase().startsWith("pt");
  const txt = pt
    ? {
        pause: "Pausar",
        play: "Reproduzir",
        zoom: "Ampliar",
        close: "Fechar vídeo ampliado",
        hint: phone.matches ? "Toque no vídeo ou em Ampliar para ver em tela cheia"
                            : "Clique no vídeo ou em Ampliar para ver em tela cheia",
      }
    : {
        pause: "Pause",
        play: "Play",
        zoom: "Enlarge",
        close: "Close enlarged video",
        hint: phone.matches ? "Tap the video or Enlarge for full screen"
                            : "Click the video or Enlarge for full screen",
      };

  const figure = vids[0].closest("figure");
  const cap = figure?.querySelector("figcaption");
  if (cap) {
    const hint = document.createElement("span");
    hint.className = "tap-hint";
    hint.textContent = txt.hint;
    cap.appendChild(hint);
  }

  // Lightbox fallback when requestFullscreen is unavailable or rejected.
  let lightbox = null;
  let lastFocus = null;
  const closeLightbox = () => {
    if (!lightbox) return;
    const lv = lightbox.querySelector("video");
    if (lv) lv.pause();
    lightbox.remove();
    lightbox = null;
    lastFocus?.focus?.();
    lastFocus = null;
  };
  const openLightbox = (v) => {
    closeLightbox();
    lastFocus = document.activeElement;
    const src = v.currentSrc || v.querySelector("source")?.getAttribute("src");
    if (!src) return;
    const wrap = document.createElement("div");
    wrap.className = "demo-lightbox";
    wrap.setAttribute("role", "dialog");
    wrap.setAttribute("aria-modal", "true");

    const inner = document.createElement("div");
    inner.className = "demo-lightbox-inner";

    const closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.className = "demo-lightbox-close";
    closeBtn.setAttribute("aria-label", txt.close);
    closeBtn.textContent = "×";
    closeBtn.addEventListener("click", closeLightbox);

    const lv = document.createElement("video");
    lv.src = src;
    lv.controls = true;
    lv.muted = true;
    lv.loop = true;
    lv.playsInline = true;
    lv.poster = v.poster || "";
    lv.addEventListener("loadedmetadata", () => {
      try { lv.currentTime = v.currentTime || 0; } catch (_) {}
      if (!calmo) lv.play().catch(() => {});
    }, { once: true });

    wrap.addEventListener("click", (e) => {
      if (e.target === wrap) closeLightbox();
    });
    inner.append(closeBtn, lv);
    wrap.appendChild(inner);
    document.body.appendChild(wrap);
    lightbox = wrap;
    closeBtn.focus();
  };

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && lightbox) closeLightbox();
  });

  const openFullscreen = async (v, lado) => {
    if (document.fullscreenElement || lightbox) return;
    try {
      if (v.requestFullscreen) {
        await v.requestFullscreen();
        if (phone.matches) await screen.orientation?.lock?.(lado).catch(() => {});
        return;
      }
      if (v.webkitEnterFullscreen) {
        v.webkitEnterFullscreen();
        return;
      }
    } catch (_) {}
    openLightbox(v);
  };

  let userPaused = calmo;

  for (const v of vids) {
    if (calmo) {
      v.removeAttribute("autoplay");
      v.pause();
      v.controls = true;
    }
    const lado = Number(v.getAttribute("height")) > Number(v.getAttribute("width")) ? "portrait" : "landscape";

    // Build Pause/Play + highlighted Fullscreen buttons in the bar below each video.
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
        if (v.paused) { userPaused = false; v.play().catch(() => {}); }
        else { userPaused = true; v.pause(); }
      });
      v.addEventListener("play", syncPlay);
      v.addEventListener("pause", syncPlay);
      syncPlay();

      const btnZoom = document.createElement("button");
      btnZoom.type = "button";
      btnZoom.className = "demo-btn demo-btn-zoom";
      btnZoom.textContent = "⛶ " + txt.zoom;
      btnZoom.addEventListener("click", () => openFullscreen(v, lado));

      ctrl.append(btnPlay, btnZoom);
      bar.appendChild(ctrl);
    }

    v.addEventListener("click", async () => {
      if (document.fullscreenElement || lightbox) return;
      await openFullscreen(v, lado);
      if (!calmo && !userPaused && !v.paused) v.play().catch(() => {});
    });
  }

  // Orientation tabs: desktop starts on Landscape (full figure width); phone starts on Portrait.
  const tabBar = figure?.querySelector(".demo-tabs");
  const tabs = [...(figure?.querySelectorAll("[data-demo-tab]") || [])];
  const panels = [...(figure?.querySelectorAll("[data-demo-panel]") || [])];
  if (tabBar && tabs.length && panels.length) {
    tabBar.hidden = false;
    const activate = (which) => {
      for (const t of tabs) {
        t.setAttribute("aria-selected", String(t.dataset.demoTab === which));
      }
      for (const p of panels) {
        const active = p.dataset.demoPanel === which;
        p.hidden = !active;
        const v = p.querySelector("video");
        if (!v) continue;
        if (active) {
          if (!calmo && !userPaused) v.play().catch(() => {});
        } else {
          v.pause();
        }
      }
    };
    for (const t of tabs) {
      t.addEventListener("click", () => activate(t.dataset.demoTab));
    }
    activate(phone.matches ? "tall" : "wide");
  }

  document.addEventListener("fullscreenchange", () => {
    if (!document.fullscreenElement) screen.orientation?.unlock?.();
  });
})();
