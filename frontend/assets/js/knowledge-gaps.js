let claudeConfigured = false;
let gapAnalyses = [];
let activeAnalysisId = null;

function gapEscapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function gapFormatDate(iso) {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

async function loadStatus() {
  try {
    const s = await window.AIAgentApi.get("/agent/status");
    claudeConfigured = s.configured;
    const badge = document.getElementById("claude-status-badge");
    if (s.configured) {
      badge.className = "badge-pill badge-success";
      badge.innerHTML = `<span class="dot dot-success"></span> Claude connected (${s.model})`;
      document.getElementById("provider-banner").classList.add("d-none");
    } else {
      badge.className = "badge-pill badge-warning";
      badge.innerHTML = `<span class="dot dot-muted"></span> Claude not configured`;
      document.getElementById("provider-banner").classList.remove("d-none");
      document.getElementById("provider-banner-text").textContent =
        `${s.detail} You can still submit a request — it will be saved, and analyzed automatically once Claude is configured server-side.`;
    }
  } catch {
    window.AIAgentToast.show("Could not check Claude connection status.", "error");
  }
}

async function loadProjects() {
  try {
    const projects = await window.AIAgentApi.get("/projects?status=all");
    const select = document.getElementById("gap-project");
    projects.forEach((p) => {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = p.name;
      select.appendChild(opt);
    });
  } catch {
    // Non-fatal: the project picker just stays limited to "No project".
  }
}

function statusBadge(status) {
  return status === "completed"
    ? '<span class="badge-pill badge-success">Completed</span>'
    : '<span class="badge-pill badge-danger">Failed</span>';
}

function renderResult(analysis) {
  document.getElementById("gap-empty-state").classList.add("d-none");
  const panel = document.getElementById("gap-result-panel");
  panel.style.display = "";
  document.getElementById("gap-result-title").textContent = analysis.query;
  document.getElementById("gap-result-status").outerHTML = `<span id="gap-result-status">${statusBadge(analysis.status)}</span>`;

  const body = document.getElementById("gap-result-body");

  if (analysis.status === "failed") {
    body.innerHTML = `
      <div class="alert-inline visible error">${gapEscapeHtml(analysis.error || "This analysis could not be completed.")}</div>
    `;
    return;
  }

  const section = (title, items) =>
    items && items.length
      ? `<div class="knowledge-gap-section"><h6>${title}</h6><ul>${items.map((i) => `<li>${gapEscapeHtml(i)}</li>`).join("")}</ul></div>`
      : "";

  body.innerHTML = [
    analysis.existing_summary
      ? `<div class="knowledge-gap-section"><h6>Already covered</h6><p style="font-size:0.88rem;">${gapEscapeHtml(analysis.existing_summary)}</p></div>`
      : "",
    section("Missing", analysis.missing_items),
    section("Recommended next steps", analysis.recommended_additions),
    section("Possible duplicates", analysis.duplicate_notes),
    section("Possibly outdated", analysis.outdated_notes),
  ].join("");
}

function renderHistoryList() {
  const listEl = document.getElementById("gap-history-list");
  const emptyEl = document.getElementById("gap-history-empty");
  if (!gapAnalyses.length) {
    listEl.innerHTML = "";
    emptyEl.classList.remove("d-none");
    return;
  }
  emptyEl.classList.add("d-none");
  listEl.innerHTML = gapAnalyses
    .map(
      (a) => `
    <div class="knowledge-gap-history-row ${a.id === activeAnalysisId ? "active" : ""}" data-id="${a.id}">
      <div class="gap-query text-truncate">${gapEscapeHtml(a.query)}</div>
      <div class="gap-meta">${statusBadge(a.status)} · ${gapFormatDate(a.created_at)}${a.project_name ? ` · ${gapEscapeHtml(a.project_name)}` : ""}</div>
    </div>`
    )
    .join("");

  listEl.querySelectorAll("[data-id]").forEach((row) => {
    row.addEventListener("click", () => {
      const analysis = gapAnalyses.find((a) => a.id === row.dataset.id);
      if (!analysis) return;
      activeAnalysisId = analysis.id;
      renderHistoryList();
      renderResult(analysis);
    });
  });
}

async function loadHistory() {
  try {
    gapAnalyses = await window.AIAgentApi.get("/knowledge/gaps");
    renderHistoryList();
  } catch {
    window.AIAgentToast.show("Could not load past analyses.", "error");
  }
}

function setQueryError(message) {
  const el = document.querySelector('[data-error-for="query"]');
  el.textContent = message || "";
  el.classList.toggle("visible", Boolean(message));
}

async function runAnalysis() {
  const query = document.getElementById("gap-query").value.trim();
  const projectId = document.getElementById("gap-project").value;
  setQueryError("");

  if (query.length < 3) {
    setQueryError("Describe what you want to analyze in a bit more detail.");
    return;
  }

  const btn = document.getElementById("gap-analyze-btn");
  const originalLabel = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Analyzing…`;

  try {
    const analysis = await window.AIAgentApi.post("/knowledge/gaps", {
      query,
      project_id: projectId || undefined,
    });
    activeAnalysisId = analysis.id;
    renderResult(analysis);
    await loadHistory();
    document.getElementById("gap-query").value = "";
  } catch (err) {
    if (err.status === 422) {
      const fieldError = (err.fieldErrors || []).find((fe) => fe.field === "query");
      setQueryError(fieldError ? fieldError.message : err.message);
    } else if (err.status === 503) {
      // The query was still persisted server-side (never lost) — refresh
      // history so the user can see it recorded as failed, then show it.
      await loadHistory();
      const latest = gapAnalyses[0];
      if (latest) {
        activeAnalysisId = latest.id;
        renderHistoryList();
        renderResult(latest);
      }
      window.AIAgentToast.show(err.message, "error");
    } else {
      window.AIAgentToast.show(err.message, "error");
    }
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalLabel;
  }
}

async function init() {
  const user = await window.AppShell.initAppShell("knowledge-gaps");
  if (!user) return;

  document.getElementById("gap-analyze-btn").addEventListener("click", runAnalysis);
  document.getElementById("gap-query").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) runAnalysis();
  });

  await Promise.all([loadStatus(), loadProjects(), loadHistory()]);
}

init();
