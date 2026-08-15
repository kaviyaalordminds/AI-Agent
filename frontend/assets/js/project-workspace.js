const projectId = new URLSearchParams(window.location.search).get("id");
let currentProject = null;

function formatDateFull(iso) {
  return new Date(iso).toLocaleDateString(undefined, { month: "long", day: "numeric", year: "numeric" });
}

const _loadedTabs = new Set();

function initTabs() {
  document.querySelectorAll(".tab-strip button[data-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-strip button[data-tab]").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      document.querySelectorAll(".project-tab-panel").forEach((panel) => {
        panel.classList.toggle("d-none", panel.dataset.panel !== btn.dataset.tab);
      });
      // Each tab's data loads lazily, once, the first time it's opened —
      // avoids firing five API calls on page load for tabs the user may
      // never visit.
      if (_loadedTabs.has(btn.dataset.tab)) return;
      _loadedTabs.add(btn.dataset.tab);
      if (btn.dataset.tab === "history") loadProjectHistory();
      if (btn.dataset.tab === "files") loadProjectFiles();
      if (btn.dataset.tab === "knowledge") loadProjectKnowledge();
      if (btn.dataset.tab === "chat") loadProjectChat();
    });
  });
}

function pwEscapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function pwFormatDate(iso) {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const _FILE_STATUS_BADGES = {
  completed: "badge-success",
  queued: "badge-muted",
  processing: "badge-info",
  failed: "badge-danger",
  cancelled: "badge-muted",
};

function _statusBadge(status) {
  const cls = _FILE_STATUS_BADGES[status] || "badge-muted";
  const label = status.charAt(0).toUpperCase() + status.slice(1);
  return `<span class="badge-pill ${cls}">${label}</span>`;
}

async function loadProjectFiles() {
  const listEl = document.getElementById("project-files-list");
  const emptyEl = document.getElementById("project-files-empty");
  try {
    const [documents, jobs] = await Promise.all([
      window.AIAgentApi.get(`/documents?project_id=${projectId}`),
      window.AIAgentApi.get(`/jobs?project_id=${projectId}`),
    ]);

    const items = [
      ...documents.map((d) => ({
        kind: "document",
        id: d.id,
        title: d.title,
        typeLabel: d.format.toUpperCase(),
        status: d.status,
        created_at: d.created_at,
        downloadUrl: d.status === "completed" ? `${window.AIAgentApi.apiBase()}/documents/${d.id}/download` : null,
      })),
      ...jobs.map((j) => ({
        kind: "job",
        id: j.id,
        title: (j.input_metadata && (j.input_metadata.prompt || j.input_metadata.text)) || `${j.type} generation`,
        typeLabel: j.type.charAt(0).toUpperCase() + j.type.slice(1),
        status: j.status,
        created_at: j.created_at,
        downloadUrl: j.status === "completed" ? `${window.AIAgentApi.apiBase()}/jobs/${j.id}/download` : null,
      })),
    ].sort((a, b) => new Date(b.created_at) - new Date(a.created_at));

    if (!items.length) {
      emptyEl.classList.remove("d-none");
      listEl.innerHTML = "";
      return;
    }
    emptyEl.classList.add("d-none");
    listEl.innerHTML = items
      .map(
        (item) => `
      <div class="gen-list-row">
        <div class="min-width-0">
          <div class="gen-title text-truncate">${pwEscapeHtml(item.title)}</div>
          <div class="gen-meta">${item.typeLabel} · ${_statusBadge(item.status)} · ${pwFormatDate(item.created_at)}</div>
        </div>
        <div class="gen-actions">
          ${item.downloadUrl ? `<a class="btn-ghost" style="padding:0.35rem 0.6rem;" href="${item.downloadUrl}" target="_blank" rel="noopener" title="Download"><i class="bi bi-download"></i></a>` : ""}
        </div>
      </div>`
      )
      .join("");
  } catch (err) {
    window.AIAgentToast.show(err.message, "error");
  }
}

async function loadProjectKnowledge() {
  const listEl = document.getElementById("project-knowledge-list");
  const emptyEl = document.getElementById("project-knowledge-empty");
  document.getElementById("knowledge-new-analysis-link").href = `knowledge-gaps.html?project_id=${projectId}`;
  try {
    const analyses = await window.AIAgentApi.get(`/knowledge/gaps?project_id=${projectId}`);
    if (!analyses.length) {
      emptyEl.classList.remove("d-none");
      listEl.innerHTML = "";
      return;
    }
    emptyEl.classList.add("d-none");
    listEl.innerHTML = analyses
      .map(
        (a) => `
      <div class="knowledge-gap-history-row" style="cursor:default;">
        <div class="gap-query text-truncate">${pwEscapeHtml(a.query)}</div>
        <div class="gap-meta">${_statusBadge(a.status)} · ${pwFormatDate(a.created_at)}</div>
      </div>`
      )
      .join("");
  } catch (err) {
    window.AIAgentToast.show(err.message, "error");
  }
}

async function loadProjectChat() {
  const listEl = document.getElementById("project-chat-list");
  const emptyEl = document.getElementById("project-chat-empty");
  document.getElementById("chat-new-conversation-link").href = `agent.html?project_id=${projectId}`;
  try {
    const conversations = await window.AIAgentApi.get(`/agent/conversations?project_id=${projectId}`);
    if (!conversations.length) {
      emptyEl.classList.remove("d-none");
      listEl.innerHTML = "";
      return;
    }
    emptyEl.classList.add("d-none");
    listEl.innerHTML = conversations
      .map(
        (c) => `
      <a href="agent.html?conversation=${c.id}" class="gen-list-row" style="text-decoration:none; color:inherit;">
        <div class="min-width-0">
          <div class="gen-title text-truncate">${pwEscapeHtml(c.title)}</div>
          <div class="gen-meta">${pwFormatDate(c.updated_at)}</div>
        </div>
      </a>`
      )
      .join("");
  } catch (err) {
    window.AIAgentToast.show(err.message, "error");
  }
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
