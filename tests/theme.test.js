const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "..", "static", "js", "theme.js"), "utf8");

function page({ stored = null, systemDark = false, storageUnavailable = false } = {}) {
  const attributes = {};
  const buttonAttributes = {};
  const handlers = {};
  const label = { textContent: "" };
  const iconAttributes = {};
  const icon = { setAttribute(name, value) { iconAttributes[name] = value; } };
  let saved = stored;
  const button = {
    title: "",
    setAttribute(name, value) { buttonAttributes[name] = value; },
    querySelector(selector) { return selector === ".theme-label" ? label : selector === ".theme-icon-path" ? icon : null; },
    addEventListener(name, handler) { handlers[name] = handler; },
  };
  const colorPreference = {
    matches: systemDark,
    addEventListener(name, handler) { handlers[`system-${name}`] = handler; },
  };
  const document = {
    readyState: "loading",
    documentElement: { setAttribute(name, value) { attributes[name] = value; } },
    getElementById(id) { return id === "themeToggle" ? button : null; },
    addEventListener(name, handler) { handlers[name] = handler; },
  };
  const window = {
    localStorage: {
      getItem() { if (storageUnavailable) throw Error("Storage unavailable"); return saved; },
      setItem(_key, value) { if (storageUnavailable) throw Error("Storage unavailable"); saved = value; },
    },
    matchMedia() { return colorPreference; },
    addEventListener(name, handler) { handlers[name] = handler; },
  };
  vm.runInNewContext(source, { document, window });
  handlers.DOMContentLoaded();
  return {
    theme: () => attributes["data-bs-theme"],
    saved: () => saved,
    label: () => label.textContent,
    iconPath: () => iconAttributes.d,
    pressed: () => buttonAttributes["aria-pressed"],
    click: () => handlers.click(),
    systemChange(dark) { colorPreference.matches = dark; handlers["system-change"](); },
    storageChange(value) { saved = value; handlers.storage({ key: "contacthub-theme" }); },
  };
}

test("follows system preference until a theme is selected", () => {
  const view = page({ systemDark: true });
  assert.equal(view.theme(), "dark");
  assert.equal(view.label(), "Dark mode");
  assert.equal(view.pressed(), "true");
  assert.match(view.iconPath(), /^M20\.5/);
  view.systemChange(false);
  assert.equal(view.theme(), "light");
  assert.match(view.iconPath(), /^M12 8/);
});

test("toggle saves and restores the selected theme after reload", () => {
  const view = page({ systemDark: true });
  view.click();
  assert.equal(view.theme(), "light");
  assert.equal(view.saved(), "light");
  view.systemChange(true);
  assert.equal(view.theme(), "light");
  const reloaded = page({ stored: view.saved(), systemDark: true });
  assert.equal(reloaded.theme(), "light");
  reloaded.storageChange("dark");
  assert.equal(reloaded.theme(), "dark");
});

test("toggle remains usable when browser storage is blocked", () => {
  const view = page({ systemDark: false, storageUnavailable: true });
  view.click();
  assert.equal(view.theme(), "dark");
});
