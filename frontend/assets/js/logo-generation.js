const LOGO_STYLES = [
  { key: "minimalist", label: "Minimalist" },
  { key: "modern", label: "Modern" },
  { key: "vintage", label: "Vintage" },
  { key: "geometric", label: "Geometric" },
  { key: "playful", label: "Playful" },
  { key: "luxury", label: "Luxury" },
];

let selectedLogoStyle = "minimalist";
let logoJobs = [];

function downloadLogoUrl(id) {
  return `${window.AIAgentApi.apiBase()}/generation/logo/${id}/download`;
}

function renderLogoStylePicker() {
  const picker = document.getElementById("logo-style-picker");
  picker.innerHTML = LOGO_STYLES.map(
    (s) => `<button type="button" class="mode-pill ${s.key === selectedLogoStyle ? "active" : ""}" data-style="${s.key}">${s.label}</button>`
  ).join("");
  picker.querySelectorAll("[data-style]").forEach((btn) => {
    btn.addEventListener("click", () => {
      selectedLogoStyle = btn.dataset.style;
      renderLogoStylePicker();
    });
  });
}

function setLogoError(message) {
  const el = document.querySelector('[data-error-for="brand_name"]');
  el.textContent = message || "";
  el.classList.toggle("visible", Boolean(message));
}

function renderLogoProgress(job) {
  document.getElementById("logo-empty-state").classList.add("d-none");
  const panel = document.getElementById("logo-result-panel");
  panel.style.display = "";
  document.getElementById("logo-result-status").innerHTML = window.GenerationCommon.jobStatusBadge(job.status);

  const body = document.getElementById("logo-result-body");
  if (job.status === "queued" || job.status === "processing") {
    body.innerHTML = `
      <div class="gen-preview-frame mb-3">
        <div class="text-center">
          <span class="spinner-border spinner-border-sm mb-2"></span>
          <div class="gen-status-row justify-content-center">Generating your logo…</div>
        </div>
      </div>
      <div class="gen-progress-track"><div class="gen-progress-fill indeterminate"></div></div>
    `;
    return;
  }

  if (job.status === "failed") {
    const card = window.GenerationCommon.renderJobErrorCard(job, { providerLabel: "OpenAI", onRetry: generateLogo });
    body.innerHTML = card.html;
    card.wire();
    return;
  }

  if (job.status === "cancelled") {
    body.innerHTML = `<div class="alert-inline visible">This job was cancelled.</div>`;
    return;
  }

  body.innerHTML = `
    <div class="gen-preview-frame mb-3">
      <img src="${downloadLogoUrl(job.id)}" alt="Generated logo" />
    </div>
    <div class="d-flex align-items-center gap-2">
      <span style="font-size:0.78rem; color:var(--text-muted);">${job.output_metadata.size_bytes ? `${(job.output_metadata.size_bytes / 1024).toFixed(1)} KB` : ""}</span>
      <a class="btn-brand ms-auto" style="padding:0.4rem 0.9rem; font-size:0.82rem;" href="${downloadLogoUrl(job.id)}" target="_blank" rel="noopener"><i class="bi bi-download"></i> Download</a>
    </div>
  `;
}

function renderLogoList() {
  const listEl = document.getElementById("logo-list");
  const emptyEl = document.getElementById("logo-list-empty");
  emptyEl.querySelector("h6").textContent = "No logos yet";
  emptyEl.querySelector("p").textContent = "Logos you generate will be listed here.";
  if (!logoJobs.length) {
    listEl.innerHTML = "";
    emptyEl.classList.remove("d-none");
    return;
  }
  emptyEl.classList.add("d-none");
  listEl.innerHTML = logoJobs
    .map(
      (j) => `
    <div class="gen-list-row" data-id="${j.id}">
      ${j.status === "completed" ? `<img class="gen-thumb" src="${downloadLogoUrl(j.id)}" alt="" />` : `<div class="gen-thumb d-flex align-items-center justify-content-center"><i class="bi bi-vector-pen" style="color:var(--text-muted);"></i></div>`}
      <div class="min-width-0 flex-grow-1" style="cursor:pointer;" data-view="${j.id}">
        <div class="gen-title text-truncate">${window.GenerationCommon.escapeHtml((j.input_metadata && j.input_metadata.brand_name) || "Untitled logo")}</div>
        <div class="gen-meta">${window.GenerationCommon.jobStatusBadge(j.status)} · ${window.GenerationCommon.formatDate(j.created_at)}</div>
      </div>
      <div class="gen-actions">
        ${j.status === "completed" ? `<a class="btn-ghost" style="padding:0.35rem 0.6rem;" href="${downloadLogoUrl(j.id)}" target="_blank" rel="noopener" title="Download"><i class="bi bi-download"></i></a>` : ""}
      </div>
    </div>`
    )
    .join("");

  listEl.querySelectorAll("[data-view]").forEach((el) => {
    el.addEventListener("click", () => {
      const job = logoJobs.find((j) => j.id === el.dataset.view);
      if (job) renderLogoProgress(job);
    });
  });
}

async function loadLogoJobs() {
  const listEl = document.getElementById("logo-list");
  const emptyEl = document.getElementById("logo-list-empty");
  try {
    logoJobs = await window.AIAgentApi.get("/jobs?type=logo");
    renderLogoList();
  } catch (err) {
    console.error("[logo-generation] Could not load recent generations:", err);
    listEl.innerHTML = "";
    emptyEl.classList.remove("d-none");
    emptyEl.querySelector("h6").textContent = "Unable to load recent generations";
    emptyEl.querySelector("p").textContent = err.message || "Please try again.";
    window.AIAgentToast.show("Could not load your recent logos.", "error");
  }
}

async function loadLogoCapability() {
  try {
    const caps = await window.AIAgentApi.get("/system/capabilities");
    window.GenerationCommon.renderCapabilityBanner("capability-banner", caps.image);
  } catch (err) {
    console.error("[logo-generation] Could not load provider capability:", err);
  }
}

async function generateLogo() {
  const brandName = document.getElementById("logo-brand-name").value.trim();
  const colors = document.getElementById("logo-colors").value.trim();
  const description = document.getElementById("logo-description").value.trim();
  const projectId = document.getElementById("logo-project").value;
  setLogoError("");

  if (!brandName) {
    setLogoError("Name the brand this logo is for.");
    return;
  }

  const btn = document.getElementById("logo-generate-btn");
  const originalLabel = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Starting…`;

  try {
    const job = await window.AIAgentApi.post("/generation/logo", {
      brand_name: brandName,
      style: selectedLogoStyle,
      colors: colors || undefined,
      description: description || undefined,
      project_id: projectId || undefined,
    });
    renderLogoProgress(job);

    const finalJob = await window.GenerationCommon.pollJob(`/generation/logo/${job.id}`, {
      onTick: renderLogoProgress,
    });
    if (finalJob.status === "failed") {
      window.AIAgentToast.show(finalJob.error || "Logo generation failed.", "error");
    } else if (finalJob.status === "completed") {
      window.AIAgentToast.show("Logo generated.", "success");
    }
    await loadLogoJobs();
  } catch (err) {
    if (err.status === 422) {
      const fieldError = (err.fieldErrors || []).find((fe) => fe.field === "brand_name");
      if (fieldError) setLogoError(fieldError.message);
      else window.AIAgentToast.show(err.message, "error");
    } else {
      window.AIAgentToast.show(err.message, "error");
    }
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalLabel;
  }
}

async function init() {
  let user;
  try {
    user = await window.AppShell.initAppShell("logo");
  } catch (err) {
    console.error("[logo-generation] Failed to initialize app shell:", err);
    window.AIAgentToast.show("Could not load the application shell. Please refresh the page.", "error");
    return;
  }
  if (!user) return;

  try {
    renderLogoStylePicker();
    document.getElementById("logo-generate-btn").addEventListener("click", generateLogo);

    await Promise.all([loadLogoCapability(), window.GenerationCommon.loadProjectOptions("logo-project"), loadLogoJobs()]);
  } catch (err) {
    console.error("[logo-generation] Unexpected error during page initialization:", err);
    window.AIAgentToast.show("Something went wrong loading this page. Please refresh and try again.", "error");
  }
}

init();
