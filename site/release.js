// Points the download buttons straight at the files of the latest GitHub release,
// displays version + file size, reveals SHA256SUMS verification when published, shows
// immediate feedback when a download starts, and caches the API response in sessionStorage
// to avoid hitting GitHub's 60 req/h limit.
// Without JavaScript, or if the API is unreachable, the buttons keep linking to the
// release page, which always works.
(async () => {
  const CACHE_KEY = "sfs_latest_rel_v1";
  const CACHE_TTL_MS = 15 * 60 * 1000;
  const RELEASES_URL = "https://github.com/Thiopental1976/sombrero-file-search/releases/latest";
  const pt = document.documentElement.lang.toLowerCase().startsWith("pt");
  const txt = pt
    ? {
        started: "Download iniciado",
        opening: "Abrindo página de downloads no GitHub…",
        hint: "Confira os downloads do navegador. Não começou?",
        retry: "Tentar novamente",
        releases: "Página de releases",
        close: "Fechar aviso",
      }
    : {
        started: "Download started",
        opening: "Opening GitHub releases page…",
        hint: "Check your browser’s downloads. Didn’t start?",
        retry: "Try again",
        releases: "Releases page",
        close: "Dismiss notice",
      };

  // Subtle highlight on the Windows button when the visitor is on Windows.
  const plat = (navigator.userAgentData?.platform || navigator.platform || navigator.userAgent || "").toLowerCase();
  if (plat.includes("win")) {
    document.querySelectorAll(".btn-win").forEach(el => el.classList.add("is-win"));
  }

  const fmtSize = (bytes) => {
    if (!bytes || bytes <= 0) return "";
    const mb = bytes / (1024 * 1024);
    const val = mb >= 1 ? (mb >= 10 ? mb.toFixed(0) : mb.toFixed(1)) + " MB"
                        : Math.max(1, Math.round(bytes / 1024)) + " KB";
    return pt ? val.replace(".", ",") : val;
  };

  const byKind = { AppImage: null, deb: null, zip: null, sha256: null };

  // Toast feedback on click: browsers do not expose cross-origin download completion,
  // so confirm immediately that the download was triggered and offer a direct retry link.
  let toastEl = null;
  let toastTimer = null;
  const hideToast = () => {
    if (toastTimer) { clearTimeout(toastTimer); toastTimer = null; }
    if (toastEl) toastEl.hidden = true;
  };
  const showToast = (asset, href) => {
    if (!toastEl) {
      toastEl = document.createElement("div");
      toastEl.className = "dl-toast";
      toastEl.setAttribute("role", "status");
      toastEl.setAttribute("aria-live", "polite");
      document.body.appendChild(toastEl);
    }
    toastEl.replaceChildren();

    const body = document.createElement("div");
    body.className = "dl-toast-body";

    const title = document.createElement("strong");
    title.className = "dl-toast-title";
    title.textContent = asset ? txt.started : txt.opening;
    body.appendChild(title);

    if (asset && asset.name) {
      const file = document.createElement("span");
      file.className = "dl-toast-file";
      const sizeStr = fmtSize(asset.size);
      file.textContent = sizeStr ? `${asset.name} (${sizeStr})` : asset.name;
      body.appendChild(file);

      const help = document.createElement("span");
      help.className = "dl-toast-hint";
      help.append(document.createTextNode(txt.hint + " "));

      const retry = document.createElement("a");
      retry.href = href;
      retry.textContent = txt.retry;
      help.appendChild(retry);

      help.append(document.createTextNode(" · "));

      const relLink = document.createElement("a");
      relLink.href = RELEASES_URL;
      relLink.target = "_blank";
      relLink.rel = "noopener";
      relLink.textContent = txt.releases;
      help.appendChild(relLink);

      body.appendChild(help);
    }

    const close = document.createElement("button");
    close.type = "button";
    close.className = "dl-toast-close";
    close.setAttribute("aria-label", txt.close);
    close.textContent = "×";
    close.addEventListener("click", hideToast);

    toastEl.append(body, close);
    toastEl.hidden = false;

    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(hideToast, 12000);
  };

  for (const a of document.querySelectorAll("[data-dl]")) {
    a.addEventListener("click", (e) => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
      const asset = byKind[a.dataset.dl] || null;
      if (a.classList.contains("btn")) {
        a.classList.add("is-downloading");
        setTimeout(() => a.classList.remove("is-downloading"), 3500);
      }
      showToast(asset, a.href);
    });
  }

  const loadCached = () => {
    try {
      const raw = sessionStorage.getItem(CACHE_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      if (parsed && parsed.ts && (Date.now() - parsed.ts) < CACHE_TTL_MS && parsed.rel) {
        return parsed.rel;
      }
    } catch (_) {}
    return null;
  };

  const saveCache = (rel) => {
    try {
      sessionStorage.setItem(CACHE_KEY, JSON.stringify({ ts: Date.now(), rel }));
    } catch (_) {}
  };

  try {
    let rel = loadCached();
    if (!rel) {
      const r = await fetch("https://api.github.com/repos/Thiopental1976/sombrero-file-search/releases/latest",
                            { headers: { Accept: "application/vnd.github+json" } });
      if (!r.ok) return;
      rel = await r.json();
      saveCache(rel);
    }

    const ver = (rel.tag_name || "").replace(/^v/, "");
    const assets = rel.assets || [];
    const findAsset = (kind) => {
      if (kind === "sha256") return assets.find(x => (x.name || "").toLowerCase() === "sha256sums");
      if (kind === "deb") {
        return assets.find(x => (x.name || "").endsWith("_amd64.deb"))
            || assets.find(x => (x.name || "").endsWith("_all.deb"));
      }
      if (kind === "zip") return assets.find(x => (x.name || "").endsWith("-windows-x64.zip"));
      return assets.find(x => (x.name || "").endsWith(".AppImage"));
    };

    byKind.AppImage = findAsset("AppImage") || null;
    byKind.deb = findAsset("deb") || null;
    byKind.zip = findAsset("zip") || null;
    byKind.sha256 = findAsset("sha256") || null;

    for (const a of document.querySelectorAll("[data-dl]")) {
      const asset = byKind[a.dataset.dl];
      if (asset && typeof asset.browser_download_url === "string"
          && asset.browser_download_url.startsWith("https://github.com/")) {
        a.href = asset.browser_download_url;
      }
    }

    for (const el of document.querySelectorAll("[data-ver], [data-size]")) {
      const wantVer = el.hasAttribute("data-ver");
      const kind = el.getAttribute("data-size");
      const parts = [];
      if (wantVer && ver) parts.push(ver);
      if (kind && byKind[kind] && byKind[kind].size) parts.push(fmtSize(byKind[kind].size));
      if (parts.length) el.textContent = parts.join(" · ");
    }

    if (byKind.sha256) {
      document.querySelectorAll("[data-sha256-box]").forEach(el => (el.hidden = false));
    }
  } catch (_) { /* keep the release page links */ }
})();
