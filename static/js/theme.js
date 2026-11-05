(function () {
  "use strict";

  const storageKey = "contacthub-theme";
  const colorPreference = window.matchMedia?.("(prefers-color-scheme: dark)");

  function savedTheme() {
    try {
      const value = window.localStorage.getItem(storageKey);
      return value === "light" || value === "dark" ? value : null;
    } catch (_) {
      return null;
    }
  }

  let preference = savedTheme();

  function effectiveTheme() {
    return preference || (colorPreference?.matches ? "dark" : "light");
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-bs-theme", theme);
    const toggle = document.getElementById("themeToggle");
    if (!toggle) return;
    const next = theme === "dark" ? "light" : "dark";
    toggle.setAttribute("aria-label", `Switch to ${next} mode`);
    toggle.setAttribute("aria-pressed", String(theme === "dark"));
    toggle.title = `Switch to ${next} mode`;
    toggle.querySelector(".theme-label").textContent = theme === "dark" ? "Dark mode" : "Light mode";
  }

  applyTheme(effectiveTheme());

  function initializeToggle() {
    const toggle = document.getElementById("themeToggle");
    if (!toggle) return;
    applyTheme(effectiveTheme());
    toggle.addEventListener("click", () => {
      preference = effectiveTheme() === "dark" ? "light" : "dark";
      try {
        window.localStorage.setItem(storageKey, preference);
      } catch (_) {
        // The toggle still works for this page when storage is unavailable.
      }
      applyTheme(preference);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initializeToggle, { once: true });
  } else {
    initializeToggle();
  }

  colorPreference?.addEventListener?.("change", () => {
    if (!preference) applyTheme(effectiveTheme());
  });
  window.addEventListener("storage", (event) => {
    if (event.key !== storageKey) return;
    preference = savedTheme();
    applyTheme(effectiveTheme());
  });
})();
