// Points the download buttons straight at the files of the latest GitHub release.
// Without JavaScript, or if the API is unreachable, the buttons keep linking to the
// release page, which always works.
(async () => {
  try {
    const r = await fetch("https://api.github.com/repos/Thiopental1976/sombrero-file-search/releases/latest",
                          { headers: { Accept: "application/vnd.github+json" } });
    if (!r.ok) return;
    const rel = await r.json();
    const ver = (rel.tag_name || "").replace(/^v/, "");
    document.querySelectorAll("[data-ver]").forEach(el => { if (ver) el.textContent = ver; });
    for (const a of document.querySelectorAll("[data-dl]")) {
      const ext = { deb: ".deb", zip: "-windows-x64.zip" }[a.dataset.dl] || ".AppImage";
      const asset = (rel.assets || []).find(x => x.name.endsWith(ext));
      if (asset) a.href = asset.browser_download_url;
    }
  } catch (_) { /* keep the release page links */ }
})();
