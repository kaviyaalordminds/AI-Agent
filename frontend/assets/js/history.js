let historyPage = 1;
const HISTORY_PAGE_SIZE = 20;
let historyTotal = 0;

function currentHistoryFilters() {
  const params = new URLSearchParams();
  const search = document.getElementById("history-search").value.trim();
  const type = document.getElementById("history-type-filter").value;
  const status = document.getElementById("history-status-filter").value;
  const projectId = document.getElementById("history-project-filter").value;
  if (search) params.set("search", search);
  if (type) params.set("type", type);
  if (status) params.set("status", status);
  if (projectId) params.set("project_id", projectId);
  params.set("page", historyPage);
  params.set("page_size", HISTORY_PAGE_SIZE);
  return params;
}

function hasActiveFilters() {
  return (
    document.getElementById("history-search").value.trim() ||
    document.getElementById("history-type-filter").value ||
    document.getElementById("history-status-filter").value ||
    document.getElementById("history-project-filter").value
  );
}

async function loadHistory() {
  const listEl = document.getElementById("history-list");
  const emptyEl = document.getElementById("history-empty");

  try {
    const res = await window.AIAgentApi.get(`/history?${currentHistoryFilters().toString()}`);
    historyTotal = res.total;

    if (!res.items.length) {
      listEl.innerHTML = "";
      emptyEl.classList.remove("d-none");
      const filtered = hasActiveFilters();
      document.getElementById("history-empty-title").textContent = filtered
        ? "No matching history"
        : "No history yet";
      document.getElementById("history-empty-subtitle").textContent = filtered
        ? "Try adjusting or clearing your filters."
        : "Actions you and Shadow AI take across every tool will appear here once those modules are built.";
    } else {
      emptyEl.classList.add("d-none");
      listEl.innerHTML = window.HistoryCommon.renderHistoryRows(res.items, { showProject: true });
      window.HistoryCommon.wireHistoryDeleteButtons(listEl, loadHistory);
    }

    updatePagination();
  } catch (err) {
    window.AIAgentToast.show(err.message, "error");
  }
}

function updatePagination() {
  const start = historyTotal === 0 ? 0 : (historyPage - 1) * HISTORY_PAGE_SIZE + 1;
  const end = Math.min(historyPage * HISTORY_PAGE_SIZE, historyTotal);
  document.getElementById("history-pagination-summary").textContent =
    historyTotal === 0 ? "" : `Showing ${start}–${end} of ${historyTotal}`;
  document.getElementById("history-prev-page").disabled = historyPage <= 1;
  document.getElementById("history-next-page").disabled = end >= historyTotal;
}

async function loadProjectFilterOptions() {
  try {
    const projects = await window.AIAgentApi.get("/projects?status=all");
    const select = document.getElementById("history-project-filter");
    projects.forEach((p) => {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = p.name;
      select.appendChild(opt);
    });
  } catch {
    // Non-fatal: the project filter just stays limited to "All projects".
  }
}

function initFilters() {
  const debouncedReload = debounce(() => {
    historyPage = 1;
    loadHistory();
  }, 300);

  document.getElementById("history-search").addEventListener("input", debouncedReload);
  ["history-type-filter", "history-status-filter", "history-project-filter"].forEach((id) => {
    document.getElementById(id).addEventListener("change", () => {
      historyPage = 1;
      loadHistory();
    });
  });

  document.getElementById("history-clear-filters").addEventListener("click", () => {
    document.getElementById("history-search").value = "";
    document.getElementById("history-type-filter").value = "";
    document.getElementById("history-status-filter").value = "";
    document.getElementById("history-project-filter").value = "";
    historyPage = 1;
    loadHistory();
  });

  document.getElementById("history-prev-page").addEventListener("click", () => {
    if (historyPage > 1) {
      historyPage--;
      loadHistory();
    }
  });
  document.getElementById("history-next-page").addEventListener("click", () => {
    historyPage++;
    loadHistory();
  });
}

function debounce(fn, delay) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}

async function init() {
  const user = await window.AppShell.initAppShell("history");
  if (!user) return;

  initFilters();

  const typeFromUrl = new URLSearchParams(window.location.search).get("type");
  if (typeFromUrl) {
    document.getElementById("history-type-filter").value = typeFromUrl;
  }

  await loadProjectFilterOptions();
  loadHistory();
}

init();
