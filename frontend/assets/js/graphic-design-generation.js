const DESIGN_TYPES = [
  { key: "social_media_post", label: "Social media post" },
  { key: "banner", label: "Banner" },
  { key: "flyer", label: "Flyer" },
  { key: "business_card", label: "Business card" },
  { key: "presentation_cover", label: "Presentation cover" },
  { key: "other", label: "Other" },
];

const DESIGN_ASPECTS = [
  { key: "1:1", label: "Square", width: 1024, height: 1024, w: 22, h: 22 },
  { key: "3:4", label: "Portrait", width: 896, height: 1152, w: 17, h: 22 },
  { key: "4:3", label: "Landscape", width: 1152, height: 896, w: 22, h: 17 },
  { key: "16:9", label: "Widescreen", width: 1344, height: 768, w: 22, h: 13 },
];

let selectedDesignType = "other";
let selectedDesignAspect = "1:1";
let designJobs = [];

function downloadDesignUrl(id) {
  return `${window.AIAgentApi.apiBase()}/generation/design/${id}/download`;
}

function renderDesignTypePicker() {
  const picker = document.getElementById("design-type-picker");
  picker.innerHTML = DESIGN_TYPES.map(
    (t) => `<button type="button" class="mode-pill ${t.key === selectedDesignType ? "active" : ""}" data-type="${t.key}">${t.label}</button>`
  ).join("");
  picker.querySelectorAll("[data-type]").forEach((btn) => {
    btn.addEventListener("click", () => {
      selectedDesignType = btn.dataset.type;
      renderDesignTypePicker();
    });
  });
}

function renderDesignAspectPicker() {
  const picker = document.getElementById("design-aspect-picker");
  picker.innerHTML = DESIGN_ASPECTS.map(
    (a) => `
    <button type="button" class="aspect-pill ${a.key === selectedDesignAspect ? "active" : ""}" data-aspect="${a.key}">
      <span class="aspect-swatch" style="width:${a.w}px; height:${a.h}px;"></span>
      ${a.label}
    </button>`
  ).join("");
  picker.querySelectorAll("[data-aspect]").forEach((btn) => {
    btn.addEventListener("click", () => {
      selectedDesignAspect = btn.dataset.aspect;
      renderDesignAspectPicker();
    });
  });
}

function setDesignError(message) {
  const el = document.querySelector('[data-error-for="prompt"]');
  el.textContent = message || "";
  el.classList.toggle("visible", Boolean(message));
}

function renderDesignProgress(job) {
  document.getElementById("design-empty-state").classList.add("d-none");
  const panel = document.getElementById("design-result-panel");
  panel.style.display = "";
  document.getElementById("design-result-status").innerHTML = window.GenerationCommon.jobStatusBadge(job.status);

  const body = document.getElementById("design-result-body");
  if (job.status === "queued" || job.status === "processing") {
    body.innerHTML = `
      <div class="gen-preview-frame mb-3">
        <div class="text-center">
          <span class="spinner-border spinner-border-sm mb-2"></span>
          <div class="gen-status-row justify-content-center">Generating your design…</div>
        </div>
      </div>
      <div class="gen-progress-track"><div class="gen-progress-fill indeterminate"></div></div>
    `;
    return;
  }

  if (job.status === "failed") {
    const card = window.GenerationCommon.renderJobErrorCard(job, { providerLabel: "OpenAI", onRetry: generateDesign });
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
      <img src="${downloadDesignUrl(job.id)}" alt="Generated design" />
    </div>
    <div class="d-flex align-items-center gap-2">
      <span style="font-size:0.78rem; color:var(--text-muted);">${job.output_metadata.size_bytes ? `${(job.output_metadata.size_bytes / 1024).toFixed(1)} KB` : ""}</span>
      <a class="btn-brand ms-auto" style="padding:0.4rem 0.9rem; font-size:0.82rem;" href="${downloadDesignUrl(job.id)}" target="_blank" rel="noopener"><i class="bi bi-download"></i> Download</a>
    </div>
  `;
}

function designTypeLabel(key) {
  const match = DESIGN_TYPES.find((t) => t.key === key);
  return match ? match.label : "Design";
}

function renderDesignList() {
  const listEl = document.getElementById("design-list");
  const emptyEl = document.getElementById("design-list-empty");
  emptyEl.querySelector("h6").textContent = "No designs yet";
  emptyEl.querySelector("p").textContent = "Designs you generate will be listed here.";
  if (!designJobs.length) {
    listEl.innerHTML = "";
    emptyEl.classList.remove("d-none");
    return;
  }
  emptyEl.classList.add("d-none");
  listEl.innerHTML = designJobs
    .map(
      (j) => `
    <div class="gen-list-row" data-id="${j.id}">
      ${j.status === "completed" ? `<img class="gen-thumb" src="${downloadDesignUrl(j.id)}" alt="" />` : `<div class="gen-thumb d-flex align-items-center justify-content-center"><i class="bi bi-palette" style="color:var(--text-muted);"></i></div>`}
      <div class="min-width-0 flex-grow-1" style="cursor:pointer;" data-view="${j.id}">
        <div class="gen-title text-truncate">${window.GenerationCommon.escapeHtml(designTypeLabel(j.input_metadata && j.input_metadata.design_type))}</div>
        <div class="gen-meta">${window.GenerationCommon.jobStatusBadge(j.status)} · ${window.GenerationCommon.formatDate(j.created_at)}</div>
      </div>
      <div class="gen-actions">
        ${j.status === "completed" ? `<a class="btn-ghost" style="padding:0.35rem 0.6rem;" href="${downloadDesignUrl(j.id)}" target="_blank" rel="noopener" title="Download"><i class="bi bi-download"></i></a>` : ""}
      </div>
    </div>`
    )
    .join("");

  listEl.querySelectorAll("[data-view]").forEach((el) => {
    el.addEventListener("click", () => {
      const job = designJobs.find((j) => j.id === el.dataset.view);
      if (job) renderDesignProgress(job);
    });
  });
}

async function loadDesignJobs() {
  const listEl = document.getElementById("design-list");
  const emptyEl = document.getElementById("design-list-empty");
  try {
    designJobs = await window.AIAgentApi.get("/jobs?type=graphic_design");
    renderDesignList();
  } catch (err) {
    console.error("[graphic-design-generation] Could not load recent generations:", err);
    listEl.innerHTML = "";
    emptyEl.classList.remove("d-none");
    emptyEl.querySelector("h6").textContent = "Unable to load recent generations";
    emptyEl.querySelector("p").textContent = err.message || "Please try again.";
    window.AIAgentToast.show("Could not load your recent designs.", "error");
  }
}

async function loadDesignCapability() {
  try {
    const caps = await window.AIAgentApi.get("/system/capabilities");
    window.GenerationCommon.renderCapabilityBanner("capability-banner", caps.image);
  } catch (err) {
    console.error("[graphic-design-generation] Could not load provider capability:", err);
  }
}

async function generateDesign() {
  const prompt = document.getElementById("design-prompt").value.trim();
  const projectId = document.getElementById("design-project").value;
  setDesignError("");

  if (!prompt) {
    setDesignError("Describe the design you want.");
    return;
  }

  const aspect = DESIGN_ASPECTS.find((a) => a.key === selectedDesignAspect) || DESIGN_ASPECTS[0];
  const btn = document.getElementById("design-generate-btn");
  const originalLabel = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Starting…`;

  try {
    const job = await window.AIAgentApi.post("/generation/design", {
      design_type: selectedDesignType,
      prompt,
      width: aspect.width,
      height: aspect.height,
      project_id: projectId || undefined,
    });
    renderDesignProgress(job);

    const finalJob = await window.GenerationCommon.pollJob(`/generation/design/${job.id}`, {
      onTick: renderDesignProgress,
    });
    if (finalJob.status === "failed") {
      window.AIAgentToast.show(finalJob.error || "Design generation failed.", "error");
    } else if (finalJob.status === "completed") {
      window.AIAgentToast.show("Design generated.", "success");
    }
    await loadDesignJobs();
  } catch (err) {
    if (err.status === 422) {
      const fieldError = (err.fieldErrors || []).find((fe) => fe.field === "prompt");
      if (fieldError) setDesignError(fieldError.message);
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
    user = await window.AppShell.initAppShell("design");
  } catch (err) {
    console.error("[graphic-design-generation] Failed to initialize app shell:", err);
    window.AIAgentToast.show("Could not load the application shell. Please refresh the page.", "error");
    return;
  }
  if (!user) return;

  try {
    renderDesignTypePicker();
    renderDesignAspectPicker();
    document.getElementById("design-generate-btn").addEventListener("click", generateDesign);

    await Promise.all([
      loadDesignCapability(),
      window.GenerationCommon.loadProjectOptions("design-project"),
      loadDesignJobs(),
    ]);
  } catch (err) {
    console.error("[graphic-design-generation] Unexpected error during page initialization:", err);
    window.AIAgentToast.show("Something went wrong loading this page. Please refresh and try again.", "error");
  }
}

init();
