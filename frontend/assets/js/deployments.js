const DEPLOY_STATUS_BADGES = {
  draft: '<span class="badge-pill badge-muted">Draft</span>',
  deploying: '<span class="badge-pill badge-info"><span class="dot dot-muted"></span> Deploying</span>',
  active: '<span class="badge-pill badge-success"><span class="dot dot-success"></span> Active</span>',
  failed: '<span class="badge-pill badge-danger"><span class="dot dot-danger"></span> Failed</span>',
  stopped: '<span class="badge-pill badge-muted">Stopped</span>',
};

const DEPLOY_TYPE_LABELS = { website: "Website", website_3d: "3D Website" };

let deployments = [];
let completedWebsites = [];
let selectedDeploymentId = null;
let newDeployModal;

function escapeHtml(str) {
  return window.GenerationCommon.escapeHtml(str);
}

function formatDate(iso) {
  return iso ? window.GenerationCommon.formatDate(iso) : "—";
}

function statusBadge(status) {
  return DEPLOY_STATUS_BADGES[status] || `<span class="badge-pill badge-muted">${escapeHtml(status)}</span>`;
}

function downloadDeploymentUrl(id) {
  return `${window.AIAgentApi.apiBase()}/deployments/${id}/download`;
}

function renderStats() {
  const el = document.getElementById("deploy-stats");
  const counts = { total: deployments.length, active: 0, failed: 0, draft: 0 };
  deployments.forEach((d) => {
    if (d.status === "active") counts.active++;
    else if (d.status === "failed") counts.failed++;
    else if (d.status === "draft") counts.draft++;
  });
  el.innerHTML = [
    { label: "Total Deployments", value: counts.total, cls: "" },
    { label: "Active", value: counts.active, cls: "text-success" },
    { label: "Failed", value: counts.failed, cls: "text-danger" },
    { label: "Drafts", value: counts.draft, cls: "text-muted" },
  ]
    .map(
      (c) => `
    <div class="surface stat-card">
      <div class="stat-value ${c.cls}">${c.value}</div>
      <div class="stat-label">${c.label}</div>
    </div>`
    )
    .join("");
}

function renderList() {
  const listEl = document.getElementById("deploy-list");
  const emptyEl = document.getElementById("deploy-empty");
  const loadingEl = document.getElementById("deploy-loading");
  loadingEl.classList.add("d-none");

  if (!deployments.length) {
    listEl.classList.add("d-none");
    emptyEl.classList.remove("d-none");
    return;
  }
  emptyEl.classList.add("d-none");
  listEl.classList.remove("d-none");

  const header = `
    <div class="deploy-table-row header">
      <span>Name</span>
      <span>Type</span>
      <span>Environment</span>
      <span>Status</span>
      <span></span>
    </div>`;

  const rows = deployments
    .map(
      (d) => `
    <div class="deploy-table-row ${d.id === selectedDeploymentId ? "active" : ""}" data-id="${d.id}">
      <span>
        <div class="deploy-row-name text-truncate">${escapeHtml(d.name)}</div>
        <div class="deploy-row-sub text-truncate">${escapeHtml(d.website_name)} · Created ${formatDate(d.created_at)}</div>
      </span>
      <span>${DEPLOY_TYPE_LABELS[d.deployment_type] || d.deployment_type}</span>
      <span style="text-transform:capitalize;">${escapeHtml(d.environment)}</span>
      <span>${statusBadge(d.status)}</span>
      <span></span>
    </div>`
    )
    .join("");

  listEl.innerHTML = header + rows;
  listEl.querySelectorAll(".deploy-table-row:not(.header)").forEach((row) => {
    row.addEventListener("click", () => selectDeployment(row.dataset.id));
  });
}

function actionButton(label, icon, handler, extraClass = "btn-ghost") {
  const id = `deploy-action-${Math.random().toString(36).slice(2, 8)}`;
  return { html: `<button type="button" class="${extraClass}" id="${id}" style="padding:0.4rem 0.9rem; font-size:0.82rem;"><i class="bi ${icon}"></i> ${label}</button>`, id, handler };
}

function renderDetail(d) {
  document.getElementById("deploy-detail-empty").classList.add("d-none");
  const panel = document.getElementById("deploy-detail-panel");
  panel.style.display = "";
  document.getElementById("deploy-detail-name").textContent = d.name;
  document.getElementById("deploy-detail-status").innerHTML = statusBadge(d.status);

  const buttons = [];
  if (d.status === "draft" || d.status === "failed" || d.status === "stopped") {
    buttons.push(actionButton(d.status === "draft" ? "Deploy" : "Redeploy", "bi-cloud-arrow-up", () => runDeploy(d.id), "btn-brand"));
  }
  if (d.status === "active") {
    buttons.push(actionButton("Redeploy", "bi-arrow-clockwise", () => runDeploy(d.id)));
    buttons.push(actionButton("Stop", "bi-stop-circle", () => runStop(d.id)));
  }
  if (d.live_url) {
    buttons.push({ html: `<a class="btn-ghost" style="padding:0.4rem 0.9rem; font-size:0.82rem;" href="${d.live_url}" target="_blank" rel="noopener"><i class="bi bi-box-arrow-up-right"></i> Open URL</a>` });
  }
  if (d.downloadable) {
    buttons.push({ html: `<a class="btn-ghost" style="padding:0.4rem 0.9rem; font-size:0.82rem;" href="${downloadDeploymentUrl(d.id)}" target="_blank" rel="noopener"><i class="bi bi-download"></i> Download</a>` });
  }
  buttons.push(actionButton("Delete", "bi-trash3", () => runDelete(d.id)));

  document.getElementById("deploy-detail-body").innerHTML = `
    ${d.status === "failed" && d.error ? `<div class="mb-3 p-2" style="background:var(--danger-bg); color:var(--danger); border-radius:var(--radius-md); font-size:0.85rem;">${escapeHtml(d.error)}</div>` : ""}
    ${d.status === "deploying" ? `<div class="gen-status-row mb-3"><span class="spinner-border spinner-border-sm"></span> Deploying…</div>` : ""}
    <div class="deploy-detail-field">
      <div class="deploy-detail-label">Website source</div>
      <div class="deploy-detail-value">${escapeHtml(d.website_name)} (${DEPLOY_TYPE_LABELS[d.deployment_type] || d.deployment_type})</div>
    </div>
    <div class="deploy-detail-field">
      <div class="deploy-detail-label">Environment</div>
      <div class="deploy-detail-value" style="text-transform:capitalize;">${escapeHtml(d.environment)}</div>
    </div>
    <div class="deploy-detail-field">
      <div class="deploy-detail-label">Provider</div>
      <div class="deploy-detail-value">${d.provider ? escapeHtml(d.provider) : "—"}</div>
    </div>
    <div class="deploy-detail-field">
      <div class="deploy-detail-label">Live URL</div>
      <div class="deploy-detail-value">${d.live_url ? `<a href="${d.live_url}" target="_blank" rel="noopener">${escapeHtml(d.live_url)}</a>` : "—"}</div>
    </div>
    <div class="deploy-detail-field">
      <div class="deploy-detail-label">Created</div>
      <div class="deploy-detail-value">${formatDate(d.created_at)}</div>
    </div>
    <div class="deploy-detail-field">
      <div class="deploy-detail-label">Last updated</div>
      <div class="deploy-detail-value">${formatDate(d.updated_at)}</div>
    </div>
    <div class="deploy-detail-field">
      <div class="deploy-detail-label">Last deployed</div>
      <div class="deploy-detail-value">${formatDate(d.deployed_at)}</div>
    </div>
    <div class="deploy-detail-actions">${buttons.map((b) => b.html).join("")}</div>
  `;
  buttons.forEach((b) => {
    if (b.id && b.handler) document.getElementById(b.id).addEventListener("click", b.handler);
  });
}

function selectDeployment(id) {
  selectedDeploymentId = id;
  const d = deployments.find((x) => x.id === id);
  if (!d) return;
  renderList();
  renderDetail(d);
}

async function loadDeployments() {
  try {
    const statusFilter = document.getElementById("deploy-status-filter").value;
    const projectFilter = document.getElementById("deploy-project-filter").value;
    const params = new URLSearchParams();
    if (statusFilter) params.set("status", statusFilter);
    if (projectFilter) params.set("project_id", projectFilter);
    const qs = params.toString();
    deployments = await window.AIAgentApi.get(`/deployments${qs ? `?${qs}` : ""}`);
    renderStats();
    renderList();
    if (selectedDeploymentId) {
      const stillThere = deployments.find((d) => d.id === selectedDeploymentId);
      if (stillThere) renderDetail(stillThere);
      else {
        selectedDeploymentId = null;
        document.getElementById("deploy-detail-panel").style.display = "none";
        document.getElementById("deploy-detail-empty").classList.remove("d-none");
      }
    }
  } catch (err) {
    console.error("[deployments] Could not load deployments:", err);
    window.AIAgentToast.show("Could not load your deployments.", "error");
  }
}

async function runDeploy(id) {
  try {
    await window.AIAgentApi.post(`/deployments/${id}/deploy`, {});
    await loadDeployments();
    const d = deployments.find((x) => x.id === id);
    if (d && d.status === "active") window.AIAgentToast.show("Deployment is now active.", "success");
    else if (d && d.status === "failed") window.AIAgentToast.show(d.error || "Deployment failed.", "error");
  } catch (err) {
    window.AIAgentToast.show(err.message || "Deployment failed.", "error");
    await loadDeployments();
  }
}

async function runStop(id) {
  const confirmed = await window.AIAgentModals.confirmAction({
    title: "Stop this deployment?",
    message: "This marks the deployment inactive. It can be redeployed later.",
    confirmLabel: "Stop",
  });
  if (!confirmed) return;
  try {
    await window.AIAgentApi.post(`/deployments/${id}/stop`, {});
    window.AIAgentToast.show("Deployment stopped.", "success");
    await loadDeployments();
  } catch (err) {
    window.AIAgentToast.show(err.message || "Could not stop this deployment.", "error");
  }
}

async function runDelete(id) {
  const d = deployments.find((x) => x.id === id);
  const confirmed = await window.AIAgentModals.confirmAction({
    title: "Delete this deployment?",
    message: `"${d ? d.name : "This deployment"}" will be permanently removed. The source website is not affected.`,
    confirmLabel: "Delete",
    danger: true,
  });
  if (!confirmed) return;
  try {
    await window.AIAgentApi.del(`/deployments/${id}`);
    window.AIAgentToast.show("Deployment deleted.", "success");
    if (selectedDeploymentId === id) {
      selectedDeploymentId = null;
      document.getElementById("deploy-detail-panel").style.display = "none";
      document.getElementById("deploy-detail-empty").classList.remove("d-none");
    }
    await loadDeployments();
  } catch (err) {
    window.AIAgentToast.show(err.message || "Could not delete this deployment.", "error");
  }
}

function setFieldError(field, message) {
  const el = document.querySelector(`[data-error-for="${field}"]`);
  if (!el) return;
  el.textContent = message || "";
  el.classList.toggle("visible", Boolean(message));
}

async function loadCompletedWebsites() {
  try {
    const websites = await window.AIAgentApi.get("/websites");
    completedWebsites = websites.filter((w) => w.status === "completed" && w.pages.length);
  } catch (err) {
    console.error("[deployments] Could not load websites:", err);
    completedWebsites = [];
  }
}

function openNewModal() {
  setFieldError("website", "");
  document.getElementById("deploy-new-name").value = "";
  document.getElementById("deploy-new-environment").value = "production";
  const select = document.getElementById("deploy-new-website");
  const noWebsites = document.getElementById("deploy-new-no-websites");
  const createBtn = document.getElementById("deploy-new-create-btn");
  if (!completedWebsites.length) {
    select.innerHTML = "";
    select.classList.add("d-none");
    noWebsites.classList.remove("d-none");
    createBtn.disabled = true;
  } else {
    select.classList.remove("d-none");
    noWebsites.classList.add("d-none");
    createBtn.disabled = false;
    select.innerHTML = completedWebsites
      .map((w) => `<option value="${w.id}">${escapeHtml(w.name)}${w.style === "3d" ? " (3D)" : ""}</option>`)
      .join("");
  }
  newDeployModal.show();
}

async function createAndDeploy() {
  const websiteId = document.getElementById("deploy-new-website").value;
  const name = document.getElementById("deploy-new-name").value.trim();
  const environment = document.getElementById("deploy-new-environment").value;
  setFieldError("website", "");

  if (!websiteId) {
    setFieldError("website", "Select a website to deploy.");
    return;
  }

  const btn = document.getElementById("deploy-new-create-btn");
  const originalLabel = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Creating…`;

  try {
    const created = await window.AIAgentApi.post("/deployments", {
      website_id: websiteId,
      name: name || undefined,
      environment,
    });
    btn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Deploying…`;
    newDeployModal.hide();
    await loadDeployments();
    selectDeployment(created.id);
    await runDeploy(created.id);
  } catch (err) {
    if (err.status === 404) {
      setFieldError("website", err.message);
    } else {
      window.AIAgentToast.show(err.message || "Could not create this deployment.", "error");
    }
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalLabel;
  }
}

async function loadCapability() {
  try {
    const caps = await window.AIAgentApi.get("/system/capabilities");
    window.GenerationCommon.renderCapabilityBanner("capability-banner", caps.deployment);
  } catch (err) {
    console.error("[deployments] Could not load provider capability:", err);
  }
}

async function init() {
  let user;
  try {
    user = await window.AppShell.initAppShell("deployments");
  } catch (err) {
    console.error("[deployments] Failed to initialize app shell:", err);
    window.AIAgentToast.show("Could not load the application shell. Please refresh the page.", "error");
    return;
  }
  if (!user) return;

  try {
    newDeployModal = new bootstrap.Modal(document.getElementById("deploy-new-modal"));
    document.getElementById("deploy-new-btn").addEventListener("click", openNewModal);
    document.getElementById("deploy-empty-new-btn").addEventListener("click", openNewModal);
    document.getElementById("deploy-new-create-btn").addEventListener("click", createAndDeploy);
    document.getElementById("deploy-status-filter").addEventListener("change", loadDeployments);
    document.getElementById("deploy-project-filter").addEventListener("change", loadDeployments);

    await Promise.all([
      loadCapability(),
      window.GenerationCommon.loadProjectOptions("deploy-project-filter"),
      loadCompletedWebsites(),
      loadDeployments(),
    ]);
  } catch (err) {
    console.error("[deployments] Unexpected error during page initialization:", err);
    window.AIAgentToast.show("Something went wrong loading this page. Please refresh and try again.", "error");
  }
}

init();
