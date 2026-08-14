const projectId = new URLSearchParams(window.location.search).get("id");
let currentProject = null;

function formatDateFull(iso) {
  return new Date(iso).toLocaleDateString(undefined, { month: "long", day: "numeric", year: "numeric" });
}

function initTabs() {
  document.querySelectorAll(".tab-strip button[data-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-strip button[data-tab]").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      document.querySelectorAll(".project-tab-panel").forEach((panel) => {
        panel.classList.toggle("d-none", panel.dataset.panel !== btn.dataset.tab);
      });
      if (btn.dataset.tab === "history") loadProjectHistory();
    });
  });
}

async function loadProject() {
  try {
    currentProject = await window.AIAgentApi.get(`/projects/${projectId}`);
  } catch (err) {
    window.AIAgentToast.show("Project not found.", "error");
    window.location.href = "projects.html";
    return;
  }

  document.getElementById("project-title-header").textContent = currentProject.name;
  document.getElementById("overview-skeleton").classList.add("d-none");
  document.getElementById("overview-content").classList.remove("d-none");

  document.getElementById("overview-name").value = currentProject.name;
  document.getElementById("overview-description").value = currentProject.description || "";
  document.getElementById("overview-created").textContent = formatDateFull(currentProject.created_at);
  document.getElementById("overview-updated").textContent = formatDateFull(currentProject.updated_at);

  const statusBadge = document.getElementById("overview-status");
  if (currentProject.status === "archived") {
    statusBadge.className = "badge-pill badge-muted";
    statusBadge.textContent = "Archived";
    document.getElementById("settings-archive-btn").textContent = "Restore";
  } else {
    statusBadge.className = "badge-pill badge-success";
    statusBadge.textContent = "Active";
  }
}

async function loadProjectHistory() {
  const listEl = document.getElementById("project-history-list");
  const emptyEl = document.getElementById("project-history-empty");
  try {
    const res = await window.AIAgentApi.get(`/history?project_id=${projectId}&page_size=50`);
    if (!res.items.length) {
      emptyEl.classList.remove("d-none");
      listEl.innerHTML = "";
      return;
    }
    emptyEl.classList.add("d-none");
    listEl.innerHTML = window.HistoryCommon.renderHistoryRows(res.items, { showProject: false });
    window.HistoryCommon.wireHistoryDeleteButtons(listEl, loadProjectHistory);
  } catch (err) {
    window.AIAgentToast.show(err.message, "error");
  }
}

function initOverviewForm() {
  const form = document.getElementById("overview-form");
  const alertEl = document.getElementById("overview-alert");
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearFieldErrors(form);
    hideAlert(alertEl);
    const btn = document.getElementById("overview-save-btn");
    setLoading(btn, true, "Saving…");
    try {
      currentProject = await window.AIAgentApi.patch(`/projects/${projectId}`, {
        name: form.name.value.trim(),
        description: form.description.value.trim() || null,
      });
      document.getElementById("project-title-header").textContent = currentProject.name;
      showAlert(alertEl, "Project updated.", "success");
    } catch (err) {
      if (!applyFieldErrorsFromApi(form, err)) showAlert(alertEl, err.message, "error");
    } finally {
      setLoading(btn, false);
    }
  });
}

function initSettingsActions() {
  document.getElementById("settings-archive-btn").addEventListener("click", async () => {
    const action = currentProject.status === "archived" ? "unarchive" : "archive";
    try {
      currentProject = await window.AIAgentApi.post(`/projects/${projectId}/${action}`);
      window.AIAgentToast.show(
        action === "archive" ? "Project archived." : "Project restored.",
        "success"
      );
      loadProject();
    } catch (err) {
      window.AIAgentToast.show(err.message, "error");
    }
  });

  document.getElementById("settings-delete-btn").addEventListener("click", async () => {
    const confirmed = await window.AIAgentModals.confirmAction({
      title: "Delete this project?",
      message: "This permanently deletes the project. This cannot be undone.",
      confirmLabel: "Delete",
      danger: true,
    });
    if (!confirmed) return;
    try {
      await window.AIAgentApi.del(`/projects/${projectId}`);
      window.AIAgentToast.show("Project deleted.", "success");
      window.location.href = "projects.html";
    } catch (err) {
      window.AIAgentToast.show(err.message, "error");
    }
  });
}

async function init() {
  if (!projectId) {
    window.location.href = "projects.html";
    return;
  }

  const user = await window.AppShell.initAppShell("projects");
  if (!user) return;

  initTabs();
  initOverviewForm();
  initSettingsActions();
  await loadProject();

  window.WorkspaceLayout.initSplitView(document.getElementById("chat-split-view"), {
    storageKey: "aiagent:split:project-chat",
    presetsEl: document.getElementById("chat-layout-presets"),
  });
  window.WorkspaceLayout.initFullscreenToggle(document.getElementById("chat-fullscreen-btn"));
}

init();
