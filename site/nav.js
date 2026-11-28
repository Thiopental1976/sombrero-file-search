// Progressive enhancement for the mobile <details class="nav-menu">:
// closes the menu when a link is chosen, when clicking outside, or on Escape.
// Without JavaScript, the native <details> toggle still works.
(() => {
  const menu = document.querySelector(".nav-menu");
  if (!menu) return;
  menu.addEventListener("click", (e) => {
    if (e.target.closest("a")) menu.open = false;
  });
  document.addEventListener("click", (e) => {
    if (menu.open && !menu.contains(e.target)) menu.open = false;
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && menu.open) {
      menu.open = false;
      menu.querySelector("summary")?.focus();
    }
  });
})();
