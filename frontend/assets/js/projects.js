let currentStatusFilter = "active";
let projectModalInstance;

function formatDate(iso) {
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function projectCardHtml(project) {
  const isArchived = project.status === "archived";
  return `
    <div class="surface project-card" data-project-id="${project.id}" data-archived="${isArchived}">
      <div class="project-card-header">
        <div class="d-flex align-items-center gap-2">
          <div class="project-icon"><i class="bi bi-kanban"></i></div>
        </div>
        <div class="dropdown" onclick="event.stopPropagation()">
          <button type="button" class="project-card-menu-btn" data-bs-toggle="dropdown" aria-expanded="false">
            <i class="bi bi-three-dots-vertical"></i>
          </button>
          <ul class="dropdown-menu dropdown-menu-end">
            <li><a class="dropdown-item" href="#" data-action="rename">Rename</a></li>
            <li><a class="dropdown-item" href="#" data-action="duplicate">Duplicate</a></li>
            <li><a class="dropdown-item" href="#" data-action="${isArchived ? "unarchive" : "archive"}">${isArchived ? "Restore" : "Archive"}</a></li>
            <li><hr class="dropdown-divider"></li>
            <li><a class="dropdown-item text-danger" href="#" data-action="delete">Delete</a></li>
          </ul>
        </div>
      </div>
      <h6>${escapeHtml(project.name)}</h6>
      <div class="project-desc">${project.description ? escapeHtml(project.description) : '<span style="opacity:0.6;">No description</span>'}</div>
      <div class="project-meta">
        <span>Updated ${formatDate(project.updated_at)}</span>
        ${isArchived ? '<span class="badge-pill badge-muted">Archived</span>' : ""}
      </div>
    </div>`;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

async function loadProjects() {
  const skeleton = document.getElementById("projects-skeleton");
  const grid = document.getElementById("project-grid");
  const empty = document.getElementById("projects-empty");
  skeleton.classList.remove("d-none");
  grid.classList.add("d-none");
  empty.classList.add("d-none");

  try {
    const projects = await window.AIAgentApi.get(`/projects?status=${currentStatusFilter}`);
    skeleton.classList.add("d-none");

    if (!projects.length) {
      empty.classList.remove("d-none");
      document.getElementById("projects-empty-title").textContent =
        currentStatusFilter === "archived" ? "No archived projects" : "No projects yet";
      document.getElementById("projects-empty-subtitle").textContent =
        currentStatusFilter === "archived"
          ? "Projects you archive will show up here."
          : "Create your first project to start organizing your work.";
      document.getElementById("empty-new-project-btn").classList.toggle(
        "d-none",
        currentStatusFilter === "archived"
      );
      grid.innerHTML = "";
      return;
    }

    grid.classList.remove("d-none");
    grid.innerHTML = projects.map(projectCardHtml).join("");
    wireCardEvents();
  } catch (err) {
    skeleton.classList.add("d-none");
    window.AIAgentToast.show(err.message, "error");
  }
}

function wireCardEvents() {
  document.querySelectorAll(".project-card").forEach((card) => {
    card.addEventListener("click", () => {
      window.location.href = `project-workspace.html?id=${card.dataset.projectId}`;
    });
  });
  document.querySelectorAll(".project-card [data-action]").forEach((link) => {
    link.addEventListener("click", async (e) => {
      e.preventDefault();
      e.stopPropagation();
      const card = link.closest(".project-card");
      const projectId = card.dataset.projectId;
      const action = link.dataset.action;
      await handleProjectAction(action, projectId, card);
    });
  });
}

async function handleProjectAction(action, projectId, card) {
  try {
    if (action === "rename") {
      openProjectModal("edit", projectId);
      return;
    }
    if (action === "duplicate") {
      await window.AIAgentApi.post(`/projects/${projectId}/duplicate`);
      window.AIAgentToast.show("Project duplicated.", "success");
      loadProjects();
      return;
    }
    if (action === "archive") {
      await window.AIAgentApi.post(`/projects/${projectId}/archive`);
      window.AIAgentToast.show("Project archived.", "success");
      loadProjects();
      return;
    }
    if (action === "unarchive") {
      await window.AIAgentApi.post(`/projects/${projectId}/unarchive`);
      window.AIAgentToast.show("Project restored.", "success");
      loadProjects();
      return;
    }
    if (action === "delete") {
      const confirmed = await window.AIAgentModals.confirmAction({
        title: "Delete this project?",
        message: "This permanently deletes the project. This cannot be undone.",
        confirmLabel: "Delete",
        danger: true,
      });
      if (!confirmed) return;
      await window.AIAgentApi.del(`/projects/${projectId}`);
      window.AIAgentToast.show("Project deleted.", "success");
      loadProjects();
      return;
    }
  } catch (err) {
    window.AIAgentToast.show(err.message, "error");
  }
}

async function openProjectModal(mode, projectId) {
  const form = document.getElementById("project-form");
  clearFieldErrors(form);
  hideAlert(document.getElementById("project-modal-alert"));
  document.getElementById("project-id").value = projectId || "";
  document.getElementById("project-modal-title").textContent =
    mode === "edit" ? "Edit project" : "New project";

  if (mode === "edit") {
    try {
      const project = await window.AIAgentApi.get(`/projects/${projectId}`);
      form.name.value = project.name;
      form.description.value = project.description || "";
    } catch (err) {
      window.AIAgentToast.show(err.message, "error");
      return;
    }
  } else {
    form.reset();
  }

  projectModalInstance.show();
}

async function init() {
  const user = await window.AppShell.initAppShell("projects");
  if (!user) return;

  document.querySelectorAll("#status-filter-toggle button").forEach((btn) => {
    btn.addEventListener("click", () => {
      currentStatusFilter = btn.dataset.statusValue;
      document
        .querySelectorAll("#status-filter-toggle button")
        .forEach((b) => b.classList.toggle("active", b === btn));
      loadProjects();
    });
  });

  document.getElementById("new-project-btn").addEventListener("click", () => openProjectModal("create"));
  document.getElementById("empty-new-project-btn").addEventListener("click", () => openProjectModal("create"));

  projectModalInstance = new bootstrap.Modal(document.getElementById("project-modal"));

  const form = document.getElementById("project-form");
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearFieldErrors(form);
    const alertEl = document.getElementById("project-modal-alert");
    hideAlert(alertEl);
    const submitBtn = document.getElementById("project-form-submit");
    setLoading(submitBtn, true, "Saving…");

    const projectId = document.getElementById("project-id").value;
    const payload = { name: form.name.value.trim(), description: form.description.value.trim() || null };

    try {
      if (projectId) {
        await window.AIAgentApi.patch(`/projects/${projectId}`, payload);
        window.AIAgentToast.show("Project updated.", "success");
      } else {
        await window.AIAgentApi.post("/projects", payload);
        window.AIAgentToast.show("Project created.", "success");
      }
      projectModalInstance.hide();
      loadProjects();
    } catch (err) {
      if (!applyFieldErrorsFromApi(form, err)) showAlert(alertEl, err.message, "error");
    } finally {
      setLoading(submitBtn, false);
    }
  });

  loadProjects();

  if (new URLSearchParams(window.location.search).get("new") === "1") {
    openProjectModal("create");
  }
}

init();
