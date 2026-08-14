/* Theme persistence. The blocking inline snippet in each page's <head>
 * (see components/theme-init-snippet.js) already applies the stored theme
 * before first paint; this module wires up the toggle control and keeps
 * later changes (including from Settings) persisted and broadcast. */
const THEME_STORAGE_KEY = "aiagent:theme";

function getStoredTheme() {
  return localStorage.getItem(THEME_STORAGE_KEY);
}

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem(THEME_STORAGE_KEY, theme);
  document.querySelectorAll("[data-theme-toggle]").forEach((el) => {
    el.querySelectorAll("button").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.themeValue === theme);
    });
  });
  window.dispatchEvent(new CustomEvent("aiagent:theme-changed", { detail: { theme } }));
}

function currentTheme() {
  return document.documentElement.getAttribute("data-theme") || "dark";
}

function initThemeToggle(root = document) {
  root.querySelectorAll("[data-theme-toggle]").forEach((toggle) => {
    toggle.querySelectorAll("button[data-theme-value]").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.themeValue === currentTheme());
      btn.addEventListener("click", () => applyTheme(btn.dataset.themeValue));
    });
  });
}

document.addEventListener("DOMContentLoaded", () => initThemeToggle());

window.AIAgentTheme = { applyTheme, currentTheme, getStoredTheme };
