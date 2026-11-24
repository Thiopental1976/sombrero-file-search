// Points the download buttons straight at the files of the latest GitHub release,
// displays version + file size, reveals SHA256SUMS verification when published, and
// caches the API response in sessionStorage to avoid hitting GitHub's 60 req/h limit.
// Without JavaScript, or if the API is unreachable, the buttons keep linking to the
// release page, which always works.
(async () => {
  const CACHE_KEY = "sfs_latest_rel_v1";
  const CACHE_TTL_MS = 15 * 60 * 1000;
  const pt = document.documentElement.lang.toLowerCase().startsWith("pt");

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

    const byKind = {
      AppImage: findAsset("AppImage"),
      deb: findAsset("deb"),
      zip: findAsset("zip"),
      sha256: findAsset("sha256"),
    };

    for (const a of document.querySelectorAll("[data-dl]")) {
      const asset = byKind[a.dataset.dl];
      if (asset && asset.browser_download_url) a.href = asset.browser_download_url;
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
