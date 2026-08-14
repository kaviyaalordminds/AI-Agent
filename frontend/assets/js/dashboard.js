const QUICK_CREATE = [
  { icon: "bi-image", label: "Image" },
  { icon: "bi-camera-reels", label: "Video" },
  { icon: "bi-mic", label: "Audio" },
  { icon: "bi-easel", label: "PPT" },
  { icon: "bi-file-earmark-text", label: "Word" },
  { icon: "bi-file-earmark-spreadsheet", label: "Excel" },
  { icon: "bi-globe", label: "Website" },
  { icon: "bi-badge-3d", label: "3D Web" },
  { icon: "bi-file-earmark-image", label: "Poster" },
  { icon: "bi-vector-pen", label: "Logo" },
];

function initQuickCreate() {
  document.getElementById("quick-create-grid").innerHTML = QUICK_CREATE.map(
    (tile) => `
    <div class="surface quick-create-tile" data-quick-create="${tile.label}">
      <i class="bi ${tile.icon}"></i>
      <span>${tile.label}</span>
      <span class="nav-link-badge">Soon</span>
    </div>`
  ).join("");
  document.querySelectorAll("[data-quick-create]").forEach((el) => {
    el.addEventListener("click", () => {
      window.AIAgentToast.show(
        `${el.dataset.quickCreate} generation is planned for a later development phase.`,
        "info"
      );
    });
  });
}

function initCommandInput() {
  document.getElementById("command-submit").addEventListener("click", submitCommand);
  document.getElementById("command-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") submitCommand();
  });
  function submitCommand() {
    const input = document.getElementById("command-input");
    const text = input.value.trim();
    if (!text) return;
    window.location.href = `agent.html?prompt=${encodeURIComponent(text)}`;
  }
}

function dashboardFormatDate(iso) {
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

async function loadDashboardProjects() {
  const skeleton = document.getElementById("dashboard-projects-skeleton");
  const empty = document.getElementById("projects-empty");
  const list = document.getElementById("dashboard-projects-list");
  skeleton.classList.remove("d-none");
  try {
    const projects = await window.AIAgentApi.get("/projects?status=active");
    skeleton.classList.add("d-none");
    if (!projects.length) {
      empty.classList.remove("d-none");
      list.innerHTML = "";
      return;
    }
    empty.classList.add("d-none");
    list.innerHTML = projects
      .slice(0, 4)
      .map(
        (p) => `
      <a href="project-workspace.html?id=${p.id}" class="d-flex align-items-center gap-3 mb-2 p-2" style="border-radius:10px; text-decoration:none; color:inherit;" onmouseover="this.style.background='var(--bg-surface-alt)'" onmouseout="this.style.background='transparent'">
        <div class="project-icon" style="width:36px;height:36px;font-size:0.95rem;"><i class="bi bi-kanban"></i></div>
        <div class="flex-grow-1 min-width-0">
          <div style="font-weight:600; font-size:0.88rem;" class="text-truncate">${dashboardEscapeHtml(p.name)}</div>
          <div style="font-size:0.76rem; color:var(--text-muted);">Updated ${dashboardFormatDate(p.updated_at)}</div>
        </div>
      </a>`
      )
      .join("");
  } catch (err) {
    skeleton.classList.add("d-none");
    window.AIAgentToast.show(err.message, "error");
  }
}

function dashboardEscapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

async function loadDashboardActivity() {
  const skeleton = document.getElementById("dashboard-activity-skeleton");
  const empty = document.getElementById("activity-empty");
  const list = document.getElementById("dashboard-activity-list");
  skeleton.classList.remove("d-none");
  try {
    const res = await window.AIAgentApi.get("/history?page_size=5");
    skeleton.classList.add("d-none");
    if (!res.items.length) {
      empty.classList.remove("d-none");
      list.innerHTML = "";
      return;
    }
    empty.classList.add("d-none");
    list.innerHTML = res.items
      .map(
        (item) => `
      <div class="d-flex align-items-center justify-content-between py-2" style="border-bottom:1px solid var(--border-subtle); font-size:0.86rem;">
        <span class="text-truncate">${dashboardEscapeHtml(item.title)}</span>
        <span style="color:var(--text-muted); font-size:0.76rem; white-space:nowrap; margin-left:0.75rem;">${dashboardFormatDate(item.created_at)}</span>
      </div>`
      )
      .join("");
  } catch (err) {
    skeleton.classList.add("d-none");
    window.AIAgentToast.show(err.message, "error");
  }
}

async function loadClaudeStatusWidget() {
  const statusEl = document.getElementById("dashboard-claude-status");
  const detailEl = document.getElementById("dashboard-claude-detail");
  try {
    const s = await window.AIAgentApi.get("/agent/status");
    if (s.configured) {
      statusEl.innerHTML = `<span class="dot dot-success"></span><span style="font-size:0.9rem;">Connected — ${s.model}</span>`;
      detailEl.textContent = "";
    } else {
      statusEl.innerHTML = `<span class="dot dot-muted"></span><span style="font-size:0.9rem;">Not configured</span>`;
      detailEl.textContent = "Set ANTHROPIC_API_KEY on the backend to enable real AI responses. Configure it from Settings.";
    }
  } catch {
    statusEl.innerHTML = `<span class="dot dot-danger"></span><span style="font-size:0.9rem;">Could not check status</span>`;
  }
}

async function init() {
  const user = await window.AppShell.initAppShell("dashboard");
  if (!user) return;

  initQuickCreate();
  initCommandInput();

  document.getElementById("dashboard-new-project-btn").addEventListener("click", () => {
    window.location.href = "projects.html?new=1";
  });

  loadDashboardProjects();
  loadDashboardActivity();
  loadClaudeStatusWidget();
}

init();
