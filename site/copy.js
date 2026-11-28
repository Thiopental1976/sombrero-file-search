// Adds a "Copy" button to each install command. Without JavaScript the commands
// stay as plain text, which still works.
(() => {
  const pt = document.documentElement.lang.toLowerCase().startsWith("pt");
  const label = pt ? "Copiar" : "Copy";
  const done = pt ? "Copiado" : "Copied";
  const failed = pt ? "Falhou" : "Failed";
  const copy = async text => {
    try { await navigator.clipboard.writeText(text); return true; } catch (_) {}
    // Fallback for pages served without HTTPS, where the clipboard API is absent
    const ta = document.createElement("textarea");
    ta.value = text; ta.setAttribute("readonly", ""); ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select();
    let ok = false; try { ok = document.execCommand("copy"); } catch (_) {}
    ta.remove(); return ok;
  };
  const selectNode = (el) => {
    try {
      const range = document.createRange();
      range.selectNodeContents(el);
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
    } catch (_) {}
  };
  for (const pre of document.querySelectorAll(".inst pre, .verify-box pre")) {
    const box = document.createElement("div"); box.className = "cmd";
    pre.replaceWith(box); box.appendChild(pre);
    const b = document.createElement("button"); b.type = "button"; b.className = "copy"; b.textContent = label;
    let timer = null;
    b.addEventListener("click", async () => {
      if (timer) clearTimeout(timer);
      b.classList.remove("ok", "err");
      const ok = await copy(pre.textContent.trim());
      if (ok) {
        b.textContent = done; b.classList.add("ok");
        timer = setTimeout(() => { b.textContent = label; b.classList.remove("ok"); }, 1600);
      } else {
        selectNode(pre);
        b.textContent = failed; b.classList.add("err");
        timer = setTimeout(() => { b.textContent = label; b.classList.remove("err"); }, 2400);
      }
    });
    box.appendChild(b);
  }
})();
