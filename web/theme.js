"use strict";

{
  const storageKey = "quellenlot-theme";
  const root = document.documentElement;
  try {
    if (localStorage.getItem(storageKey) === "light") root.dataset.theme = "light";
  } catch {
    // The static page can still switch themes if storage is unavailable.
  }

  document.addEventListener("DOMContentLoaded", () => {
    const toggle = document.getElementById("theme-toggle");
    toggle.setAttribute("aria-pressed", String(root.dataset.theme !== "light"));
    toggle.hidden = false;

    toggle.addEventListener("click", () => {
      const next = root.dataset.theme === "light" ? "dark" : "light";
      root.dataset.theme = next;
      toggle.setAttribute("aria-pressed", String(next === "dark"));
      try {
        localStorage.setItem(storageKey, next);
      } catch {
        // Keep the active theme for this page even without storage.
      }
    });
  });
}
