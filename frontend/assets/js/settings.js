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

  initAiTab(settings);
  initClaudeTab();
  initObsidianTab();
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
