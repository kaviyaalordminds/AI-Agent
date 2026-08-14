function switchSettingsTab(tabKey) {
  document.querySelectorAll("[data-settings-tab]").forEach((el) => {
    el.classList.toggle("active", el.dataset.settingsTab === tabKey);
  });
  document.querySelectorAll(".settings-tab").forEach((el) => {
    el.classList.toggle("d-none", el.id !== `tab-${tabKey}`);
  });
}

async function init() {
  const user = await window.AppShell.initAppShell("settings");
  if (!user) return;

  document.querySelectorAll("[data-settings-tab]").forEach((el) => {
    el.addEventListener("click", () => switchSettingsTab(el.dataset.settingsTab));
  });

  window.AppShell.loadSessions();

  document.getElementById("logout-all-btn").addEventListener("click", async () => {
    try {
      await window.AIAgentApi.post("/auth/logout-all", {});
      window.location.href = "login.html";
    } catch (err) {
      window.AIAgentToast.show(err.message, "error");
    }
  });

  // Load persisted settings and wire General tab controls.
  let settings;
  try {
    settings = await window.AIAgentApi.get("/users/me/settings");
  } catch (err) {
    window.AIAgentToast.show("Could not load your settings.", "error");
    return;
  }

  document.getElementById("language-select").value = settings.language;
  document.getElementById("sidebar-collapsed-toggle").checked = settings.sidebar_collapsed;

  // Theme toggle inside the settings page persists to the backend too,
  // in addition to localStorage (handled by theme.js).
  window.addEventListener("aiagent:theme-changed", async (e) => {
    try {
      await window.AIAgentApi.patch("/users/me/settings", { theme: e.detail.theme });
    } catch {
      // Non-fatal: the theme still applies locally via localStorage.
    }
  });

  document.getElementById("language-select").addEventListener("change", async (e) => {
    try {
      await window.AIAgentApi.patch("/users/me/settings", { language: e.target.value });
      window.AIAgentToast.show("Language preference saved.", "success");
    } catch (err) {
      window.AIAgentToast.show(err.message, "error");
    }
  });

  document.getElementById("sidebar-collapsed-toggle").addEventListener("change", async (e) => {
    try {
      await window.AIAgentApi.patch("/users/me/settings", { sidebar_collapsed: e.target.checked });
      window.AIAgentToast.show("Sidebar preference saved.", "success");
    } catch (err) {
      window.AIAgentToast.show(err.message, "error");
    }
  });
}

init();
