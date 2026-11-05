(function () {
  "use strict";

  const storageKey = "contacthub-theme";
  const colorPreference = window.matchMedia?.("(prefers-color-scheme: dark)");
  const sunPath = "M12 8a4 4 0 1 0 0 8a4 4 0 1 0 0-8 M12 2v2m0 16v2M4.93 4.93l1.42 1.42m11.3 11.3 1.42 1.42M2 12h2m16 0h2M4.93 19.07l1.42-1.42m11.3-11.3 1.42-1.42";
  const moonPath = "M20.5 14.1A8.5 8.5 0 0 1 9.9 3.5 8.5 8.5 0 1 0 20.5 14.1Z";

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
    toggle.querySelector(".theme-icon-path").setAttribute("d", theme === "dark" ? moonPath : sunPath);
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
