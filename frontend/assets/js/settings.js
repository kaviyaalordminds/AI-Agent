const SETTINGS_MODES = [
  { key: "chat", label: "Chat", icon: "bi-chat-dots" },
  { key: "knowledge", label: "Knowledge", icon: "bi-diagram-3" },
  { key: "create", label: "Create", icon: "bi-magic" },
  { key: "project", label: "Project", icon: "bi-kanban" },
  { key: "research", label: "Research", icon: "bi-search" },
  { key: "developer", label: "Developer", icon: "bi-code-slash" },
  { key: "automation", label: "Automation", icon: "bi-gear-wide-connected" },
];

const KNOWLEDGE_UPDATE_POLICIES = [
  {
    key: "auto",
    label: "Auto",
    icon: "bi-lightning-charge",
    desc: "Apply proposed vault updates automatically.",
  },
  {
    key: "approval",
    label: "Approval",
    icon: "bi-hand-index-thumb",
    desc: "Always ask before any vault update is applied.",
  },
  {
    key: "smart_auto",
    label: "Smart Auto",
    icon: "bi-stars",
    desc: "Apply low-risk updates automatically; ask before anything destructive.",
  },
];

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
  // Sidebar collapse state: localStorage (via nav.js) is the authoritative,
  // instantly-applied source of truth — the backend field is a synced
  // mirror, not the source, so this checkbox reflects what's actually on
  // screen right now rather than possibly-stale DB state.
  document.getElementById("sidebar-collapsed-toggle").checked = window.AppShell.isSidebarCollapsed();

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
    // Apply immediately via the shared sidebar state (updates the DOM +
    // localStorage on this page right away), then mirror it to the backend
    // so it's remembered account-wide.
    window.AppShell.applySidebarCollapsed(e.target.checked);
    try {
      await window.AIAgentApi.patch("/users/me/settings", { sidebar_collapsed: e.target.checked });
      window.AIAgentToast.show("Sidebar preference saved.", "success");
    } catch (err) {
      window.AIAgentToast.show(err.message, "error");
    }
  });

  initAiTab(settings);
  initClaudeTab();
  initObsidianTab();
  initStorageTab();
  initSystemStatusTab();
  initWorkspaceTab(settings);
  initNotificationsTab(settings);
}

const WORKSPACE_SPLIT_RATIOS = [
  { key: "40-60", ratio: 40, label: "40 / 60" },
  { key: "50-50", ratio: 50, label: "50 / 50" },
  { key: "60-40", ratio: 60, label: "60 / 40" },
];

async function saveWorkspaceSettings(settings, patch, successMessage) {
  try {
    settings.workspace_settings = { ...(settings.workspace_settings || {}), ...patch };
    await window.AIAgentApi.patch("/users/me/settings", { workspace_settings: settings.workspace_settings });
    window.AIAgentToast.show(successMessage, "success");
  } catch (err) {
    window.AIAgentToast.show(err.message, "error");
  }
}

function initWorkspaceTab(settings) {
  const landingSelect = document.getElementById("workspace-landing-page-select");
  const landingPage = (settings.workspace_settings && settings.workspace_settings.default_landing_page) || "dashboard.html";
  landingSelect.value = landingPage;
  landingSelect.addEventListener("change", async (e) => {
    await saveWorkspaceSettings(settings, { default_landing_page: e.target.value }, "Default landing page saved.");
  });

  const ratioPicker = document.getElementById("workspace-split-ratio-picker");
  const defaultRatio = (settings.workspace_settings && settings.workspace_settings.default_split_ratio) || 50;

  function renderRatioPicker(selected) {
    ratioPicker.innerHTML = WORKSPACE_SPLIT_RATIOS.map(
      (r) => `<button type="button" class="mode-pill ${r.ratio === selected ? "active" : ""}" data-ratio="${r.ratio}">${r.label}</button>`
    ).join("");
    ratioPicker.querySelectorAll("[data-ratio]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const ratio = Number(btn.dataset.ratio);
        renderRatioPicker(ratio);
        // Mirror to localStorage immediately (same pattern as sidebar collapse)
        // so workspace-layout.js can read it synchronously with no API round trip.
        localStorage.setItem("aiagent:workspace-default-split-ratio", String(ratio));
        await saveWorkspaceSettings(settings, { default_split_ratio: ratio }, "Default split-view ratio saved.");
      });
    });
  }
  renderRatioPicker(defaultRatio);
  if (settings.workspace_settings && settings.workspace_settings.default_split_ratio) {
    localStorage.setItem("aiagent:workspace-default-split-ratio", String(settings.workspace_settings.default_split_ratio));
  }
}

const NOTIFICATION_TOGGLES = [
  { id: "notif-enabled-toggle", field: "enabled", default: true },
  { id: "notif-email-toggle", field: "email_notifications", default: false },
  { id: "notif-generation-completed-toggle", field: "generation_completed", default: true },
  { id: "notif-generation-failed-toggle", field: "generation_failed", default: true },
  { id: "notif-project-toggle", field: "project_updates", default: true },
  { id: "notif-security-toggle", field: "security_alerts", default: true },
];

function initNotificationsTab(settings) {
  const stored = settings.notification_settings || {};

  NOTIFICATION_TOGGLES.forEach(({ id, field, default: def }) => {
    const el = document.getElementById(id);
    el.checked = field in stored ? Boolean(stored[field]) : def;
  });

  NOTIFICATION_TOGGLES.forEach(({ id, field }) => {
    document.getElementById(id).addEventListener("change", async (e) => {
      try {
        settings.notification_settings = { ...(settings.notification_settings || {}), [field]: e.target.checked };
        await window.AIAgentApi.patch("/users/me/settings", { notification_settings: settings.notification_settings });
        window.AIAgentToast.show("Notification preference saved.", "success");
      } catch (err) {
        window.AIAgentToast.show(err.message, "error");
      }
    });
  });
}

async function loadStorageStatus() {
  const statusEl = document.getElementById("storage-settings-status");
  const detailEl = document.getElementById("storage-settings-detail");
  statusEl.innerHTML = `<span class="dot dot-muted"></span><span style="font-size:0.9rem;">Checking…</span>`;
  try {
    const capabilities = await window.AIAgentApi.get("/system/capabilities");
    const storage = capabilities.storage;
    statusEl.innerHTML = storage.available
      ? `<span class="dot dot-success"></span><span style="font-size:0.9rem;">Available — ${storage.provider}</span>`
      : `<span class="dot dot-danger"></span><span style="font-size:0.9rem;">Unavailable</span>`;
    detailEl.textContent = storage.reason;
  } catch (err) {
    statusEl.innerHTML = `<span class="dot dot-danger"></span><span style="font-size:0.9rem;">Could not check status</span>`;
    detailEl.textContent = err.message;
  }
}

function initStorageTab() {
  loadStorageStatus();
}

let systemStatusTabLoaded = false;

function initSystemStatusTab() {
  document.querySelector('[data-settings-tab="system-status"]').addEventListener("click", () => {
    if (systemStatusTabLoaded) return;
    systemStatusTabLoaded = true;
    window.SystemStatus.loadSystemStatus("settings-capability-grid", "settings-health-list");
  });
}

function initAiTab(settings) {
  const picker = document.getElementById("ai-default-mode-picker");
  const defaultMode = (settings.ai_settings && settings.ai_settings.default_mode) || "chat";

  function render(selected) {
    picker.innerHTML = SETTINGS_MODES.map(
      (m) => `<button type="button" class="mode-pill ${m.key === selected ? "active" : ""}" data-mode="${m.key}"><i class="bi ${m.icon}"></i> ${m.label}</button>`
    ).join("");
    picker.querySelectorAll("[data-mode]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        render(btn.dataset.mode);
        try {
          settings.ai_settings = { ...(settings.ai_settings || {}), default_mode: btn.dataset.mode };
          await window.AIAgentApi.patch("/users/me/settings", { ai_settings: settings.ai_settings });
          window.AIAgentToast.show("Default mode saved.", "success");
        } catch (err) {
          window.AIAgentToast.show(err.message, "error");
        }
      });
    });
  }
  render(defaultMode);

  const policyPicker = document.getElementById("ai-knowledge-policy-picker");
  const policyDesc = document.getElementById("ai-knowledge-policy-desc");
  const knowledgePolicy = (settings.ai_settings && settings.ai_settings.knowledge_update_policy) || "smart_auto";

  function renderPolicy(selected) {
    const active = KNOWLEDGE_UPDATE_POLICIES.find((p) => p.key === selected) || KNOWLEDGE_UPDATE_POLICIES[2];
    policyPicker.innerHTML = KNOWLEDGE_UPDATE_POLICIES.map(
      (p) => `<button type="button" class="mode-pill ${p.key === selected ? "active" : ""}" data-policy="${p.key}"><i class="bi ${p.icon}"></i> ${p.label}</button>`
    ).join("");
    policyDesc.textContent = `${active.desc} Saved now — applies once the agent can propose automatic vault updates from Knowledge Gap analysis (planned).`;
    policyPicker.querySelectorAll("[data-policy]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        renderPolicy(btn.dataset.policy);
        try {
          settings.ai_settings = { ...(settings.ai_settings || {}), knowledge_update_policy: btn.dataset.policy };
          await window.AIAgentApi.patch("/users/me/settings", { ai_settings: settings.ai_settings });
          window.AIAgentToast.show("Knowledge auto-update policy saved.", "success");
        } catch (err) {
          window.AIAgentToast.show(err.message, "error");
        }
      });
    });
  }
  renderPolicy(knowledgePolicy);
}

async function loadClaudeStatus() {
  const statusEl = document.getElementById("claude-settings-status");
  const detailEl = document.getElementById("claude-settings-detail");
  statusEl.innerHTML = `<span class="dot dot-muted"></span><span style="font-size:0.9rem;">Checking…</span>`;
  try {
    const s = await window.AIAgentApi.get("/agent/status");
    if (s.configured) {
      statusEl.innerHTML = `<span class="dot dot-success"></span><span style="font-size:0.9rem;">Connected — ${s.model}</span>`;
    } else {
      statusEl.innerHTML = `<span class="dot dot-muted"></span><span style="font-size:0.9rem;">Not configured</span>`;
    }
    detailEl.textContent = s.detail;
  } catch (err) {
    statusEl.innerHTML = `<span class="dot dot-danger"></span><span style="font-size:0.9rem;">Could not check status</span>`;
    detailEl.textContent = err.message;
  }
}

function initClaudeTab() {
  loadClaudeStatus();
  document.getElementById("claude-test-connection-btn").addEventListener("click", async () => {
    await loadClaudeStatus();
    window.AIAgentToast.show("Connection status refreshed.", "info");
  });
}

async function loadObsidianStatus() {
  const statusEl = document.getElementById("obsidian-settings-status");
  const detailEl = document.getElementById("obsidian-settings-detail");
  statusEl.innerHTML = `<span class="dot dot-muted"></span><span style="font-size:0.9rem;">Checking…</span>`;
  try {
    const s = await window.AIAgentApi.get("/obsidian/status");
    if (s.connected) {
      statusEl.innerHTML = `<span class="dot dot-success"></span><span style="font-size:0.9rem;">Connected — ${s.note_count} notes</span>`;
    } else {
      statusEl.innerHTML = `<span class="dot dot-danger"></span><span style="font-size:0.9rem;">Not connected</span>`;
    }
    detailEl.textContent = s.detail;
  } catch (err) {
    statusEl.innerHTML = `<span class="dot dot-danger"></span><span style="font-size:0.9rem;">Could not check status</span>`;
    detailEl.textContent = err.message;
  }
}

function initObsidianTab() {
  loadObsidianStatus();
  document.getElementById("obsidian-test-connection-btn").addEventListener("click", async () => {
    await loadObsidianStatus();
    window.AIAgentToast.show("Connection status refreshed.", "info");
  });
}

init();
