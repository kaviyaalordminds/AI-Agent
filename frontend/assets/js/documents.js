const DOC_FORMATS = [
  { key: "markdown", label: "Markdown", icon: "bi-markdown" },
  { key: "docx", label: "Word (.docx)", icon: "bi-file-earmark-word" },
  { key: "pdf", label: "PDF", icon: "bi-file-earmark-pdf" },
];

let selectedFormat = "markdown";
let documents = [];

function docEscapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function docFormatDate(iso) {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function statusBadge(status) {
  return status === "completed"
    ? '<span class="badge-pill badge-success">Completed</span>'
    : '<span class="badge-pill badge-danger">Failed</span>';
}

function formatBadge(format) {
  const meta = DOC_FORMATS.find((f) => f.key === format);
  return `<span class="badge-pill badge-muted"><i class="bi ${meta ? meta.icon : "bi-file-earmark"}"></i> ${meta ? meta.label : format}</span>`;
}

function downloadUrl(id) {
  return `${window.AIAgentApi.apiBase()}/documents/${id}/download`;
}

async function loadStatus() {
  try {
    const s = await window.AIAgentApi.get("/agent/status");
    const badge = document.getElementById("claude-status-badge");
    const providerLabel = window.AIAgentConfig.aiProviderLabel(s.provider);
    if (s.configured) {
      badge.className = "badge-pill badge-success";
      badge.innerHTML = `<span class="dot dot-success"></span> ${providerLabel} connected (${s.model})`;
      document.getElementById("provider-banner").classList.add("d-none");
    } else {
      badge.className = "badge-pill badge-warning";
      badge.innerHTML = `<span class="dot dot-muted"></span> ${providerLabel} not configured`;
      document.getElementById("provider-banner").classList.remove("d-none");
      document.getElementById("provider-banner-text").textContent =
        `${s.detail} You can still submit a request — it will be saved, and drafted automatically once the AI provider is configured server-side.`;
    }
  } catch {
    window.AIAgentToast.show("Could not check Claude connection status.", "error");
  }
}

async function loadProjects() {
  try {
    const projects = await window.AIAgentApi.get("/projects?status=all");
    const select = document.getElementById("doc-project");
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

function renderFormatPicker() {
  const picker = document.getElementById("doc-format-picker");
  picker.innerHTML = DOC_FORMATS.map(
    (f) => `<button type="button" class="mode-pill ${f.key === selectedFormat ? "active" : ""}" data-format="${f.key}"><i class="bi ${f.icon}"></i> ${f.label}</button>`
  ).join("");
  picker.querySelectorAll("[data-format]").forEach((btn) => {
    btn.addEventListener("click", () => {
      selectedFormat = btn.dataset.format;
      renderFormatPicker();
    });
  });
}

function renderResult(doc) {
  document.getElementById("doc-empty-state").classList.add("d-none");
  const panel = document.getElementById("doc-result-panel");
  panel.style.display = "";
  document.getElementById("doc-result-title").textContent = doc.title;
  document.getElementById("doc-result-status").outerHTML = `<span id="doc-result-status">${statusBadge(doc.status)}</span>`;

  const body = document.getElementById("doc-result-body");
  if (doc.status === "failed") {
    body.innerHTML = `<div class="alert-inline visible error">${docEscapeHtml(doc.error || "This document could not be generated.")}</div>`;
    return;
  }

  body.innerHTML = `
    <div class="d-flex align-items-center gap-2 mb-3">
      ${formatBadge(doc.format)}
      <span style="font-size:0.78rem; color:var(--text-muted);">${doc.size_bytes ? `${(doc.size_bytes / 1024).toFixed(1)} KB` : ""}</span>
      <a class="btn-brand ms-auto" style="padding:0.4rem 0.9rem; font-size:0.82rem;" href="${downloadUrl(doc.id)}" target="_blank" rel="noopener"><i class="bi bi-download"></i> Download</a>
    </div>
    <div class="doc-result-preview">${docEscapeHtml(doc.content || "")}</div>
  `;
}

function renderList() {
  const listEl = document.getElementById("doc-list");
  const emptyEl = document.getElementById("doc-list-empty");
  if (!documents.length) {
    listEl.innerHTML = "";
    emptyEl.classList.remove("d-none");
    return;
  }
  emptyEl.classList.add("d-none");
  listEl.innerHTML = documents
    .map(
      (d) => `
    <div class="doc-list-row" data-id="${d.id}">
      <div class="min-width-0 flex-grow-1" style="cursor:pointer;" data-view="${d.id}">
        <div class="doc-title text-truncate">${docEscapeHtml(d.title)}</div>
        <div class="doc-meta">${formatBadge(d.format)} ${statusBadge(d.status)} · ${docFormatDate(d.created_at)}${d.project_name ? ` · ${docEscapeHtml(d.project_name)}` : ""}</div>
      </div>
      <div class="doc-actions">
        ${d.status === "completed" ? `<a class="btn-ghost" style="padding:0.35rem 0.6rem;" href="${downloadUrl(d.id)}" target="_blank" rel="noopener" title="Download"><i class="bi bi-download"></i></a>` : ""}
        <button type="button" class="btn-ghost doc-delete-btn" data-id="${d.id}" style="padding:0.35rem 0.6rem; color:var(--danger); border-color:var(--danger);" title="Delete"><i class="bi bi-trash3"></i></button>
      </div>
    </div>`
    )
    .join("");

  listEl.querySelectorAll("[data-view]").forEach((el) => {
    el.addEventListener("click", () => {
      const doc = documents.find((d) => d.id === el.dataset.view);
      if (doc) renderResult(doc);
    });
  });
  listEl.querySelectorAll(".doc-delete-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const confirmed = await window.AIAgentModals.confirmAction({
        title: "Delete this document?",
        message: "This removes it and its generated file. This cannot be undone.",
        confirmLabel: "Delete",
        danger: true,
      });
      if (!confirmed) return;
      try {
        await window.AIAgentApi.del(`/documents/${btn.dataset.id}`);
        window.AIAgentToast.show("Document deleted.", "success");
        await loadDocuments();
      } catch (err) {
        window.AIAgentToast.show(err.message, "error");
      }
    });
  });
}

async function loadDocuments() {
  try {
    documents = await window.AIAgentApi.get("/documents");
    renderList();
  } catch {
    window.AIAgentToast.show("Could not load your documents.", "error");
  }
}

function setPromptError(message) {
  const el = document.querySelector('[data-error-for="prompt"]');
  el.textContent = message || "";
  el.classList.toggle("visible", Boolean(message));
}

async function generateDocument() {
  const prompt = document.getElementById("doc-prompt").value.trim();
  const projectId = document.getElementById("doc-project").value;
  setPromptError("");

  if (prompt.length < 3) {
    setPromptError("Describe the document you want in a bit more detail.");
    return;
  }

  const btn = document.getElementById("doc-generate-btn");
  const originalLabel = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Generating…`;

  try {
    const doc = await window.AIAgentApi.post("/documents", {
      prompt,
      format: selectedFormat,
      project_id: projectId || undefined,
    });
    renderResult(doc);
    await loadDocuments();
    document.getElementById("doc-prompt").value = "";
  } catch (err) {
    if (err.status === 422) {
      const fieldError = (err.fieldErrors || []).find((fe) => fe.field === "prompt");
      setPromptError(fieldError ? fieldError.message : err.message);
    } else if (err.status === 503) {
      // The prompt was still persisted server-side (never lost) — refresh
      // the list so the user can see it recorded as failed, then show it.
      await loadDocuments();
      const latest = documents[0];
      if (latest) renderResult(latest);
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
  const user = await window.AppShell.initAppShell("documents");
  if (!user) return;

  renderFormatPicker();
  document.getElementById("doc-generate-btn").addEventListener("click", generateDocument);

  await Promise.all([loadStatus(), loadProjects(), loadDocuments()]);
}

init();
