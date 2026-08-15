const IMG_ASPECTS = [
  { key: "1:1", label: "Square", width: 1024, height: 1024, w: 22, h: 22 },
  { key: "3:4", label: "Portrait", width: 896, height: 1152, w: 17, h: 22 },
  { key: "4:3", label: "Landscape", width: 1152, height: 896, w: 22, h: 17 },
  { key: "9:16", label: "Story", width: 768, height: 1344, w: 13, h: 22 },
  { key: "16:9", label: "Widescreen", width: 1344, height: 768, w: 22, h: 13 },
];

let selectedAspect = "1:1";
let imageJobs = [];

function downloadImageUrl(id) {
  return `${window.AIAgentApi.apiBase()}/generation/image/${id}/download`;
}

function renderAspectPicker() {
  const picker = document.getElementById("img-aspect-picker");
  picker.innerHTML = IMG_ASPECTS.map(
    (a) => `
    <button type="button" class="aspect-pill ${a.key === selectedAspect ? "active" : ""}" data-aspect="${a.key}">
      <span class="aspect-swatch" style="width:${a.w}px; height:${a.h}px;"></span>
      ${a.label}
    </button>`
  ).join("");
  picker.querySelectorAll("[data-aspect]").forEach((btn) => {
    btn.addEventListener("click", () => {
      selectedAspect = btn.dataset.aspect;
      renderAspectPicker();
    });
  });
}

function setPromptError(message) {
  const el = document.querySelector('[data-error-for="prompt"]');
  el.textContent = message || "";
  el.classList.toggle("visible", Boolean(message));
}

function renderProgress(job) {
  document.getElementById("img-empty-state").classList.add("d-none");
  const panel = document.getElementById("img-result-panel");
  panel.style.display = "";
  document.getElementById("img-result-status").innerHTML = window.GenerationCommon.jobStatusBadge(job.status);

  const body = document.getElementById("img-result-body");
  if (job.status === "queued" || job.status === "processing") {
    body.innerHTML = `
      <div class="gen-preview-frame mb-3">
        <div class="text-center">
          <span class="spinner-border spinner-border-sm mb-2"></span>
          <div class="gen-status-row justify-content-center">Generating your image…</div>
        </div>
      </div>
      <div class="gen-progress-track"><div class="gen-progress-fill indeterminate"></div></div>
    `;
    return;
  }

  if (job.status === "failed") {
    const card = window.GenerationCommon.renderJobErrorCard(job, { providerLabel: "OpenAI", onRetry: generateImage });
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
      <img src="${downloadImageUrl(job.id)}" alt="Generated image" />
    </div>
    <div class="d-flex align-items-center gap-2">
      <span style="font-size:0.78rem; color:var(--text-muted);">${job.output_metadata.size_bytes ? `${(job.output_metadata.size_bytes / 1024).toFixed(1)} KB` : ""}</span>
      <a class="btn-brand ms-auto" style="padding:0.4rem 0.9rem; font-size:0.82rem;" href="${downloadImageUrl(job.id)}" target="_blank" rel="noopener"><i class="bi bi-download"></i> Download</a>
    </div>
  `;
}

function renderList() {
  const listEl = document.getElementById("img-list");
  const emptyEl = document.getElementById("img-list-empty");
  emptyEl.querySelector("h6").textContent = "No images yet";
  emptyEl.querySelector("p").textContent = "Images you generate will be listed here.";
  if (!imageJobs.length) {
    listEl.innerHTML = "";
    emptyEl.classList.remove("d-none");
    return;
  }
  emptyEl.classList.add("d-none");
  listEl.innerHTML = imageJobs
    .map(
      (j) => `
    <div class="gen-list-row" data-id="${j.id}">
      ${j.status === "completed" ? `<img class="gen-thumb" src="${downloadImageUrl(j.id)}" alt="" />` : `<div class="gen-thumb d-flex align-items-center justify-content-center"><i class="bi bi-image" style="color:var(--text-muted);"></i></div>`}
      <div class="min-width-0 flex-grow-1" style="cursor:pointer;" data-view="${j.id}">
        <div class="gen-title text-truncate">${window.GenerationCommon.escapeHtml((j.input_metadata && j.input_metadata.prompt) || "Untitled prompt")}</div>
        <div class="gen-meta">${window.GenerationCommon.jobStatusBadge(j.status)} · ${window.GenerationCommon.formatDate(j.created_at)}</div>
      </div>
      <div class="gen-actions">
        ${j.status === "completed" ? `<a class="btn-ghost" style="padding:0.35rem 0.6rem;" href="${downloadImageUrl(j.id)}" target="_blank" rel="noopener" title="Download"><i class="bi bi-download"></i></a>` : ""}
      </div>
    </div>`
    )
    .join("");

  listEl.querySelectorAll("[data-view]").forEach((el) => {
    el.addEventListener("click", () => {
      const job = imageJobs.find((j) => j.id === el.dataset.view);
      if (job) renderProgress(job);
    });
  });
}

async function loadImageJobs() {
  const listEl = document.getElementById("img-list");
  const emptyEl = document.getElementById("img-list-empty");
  try {
    imageJobs = await window.AIAgentApi.get("/jobs?type=image");
    renderList();
  } catch (err) {
    console.error("[image-generation] Could not load recent generations:", err);
    listEl.innerHTML = "";
    emptyEl.classList.remove("d-none");
    emptyEl.querySelector("h6").textContent = "Unable to load recent generations";
    emptyEl.querySelector("p").textContent = err.message || "Please try again.";
    window.AIAgentToast.show("Could not load your recent images.", "error");
  }
}

async function loadCapability() {
  try {
    const caps = await window.AIAgentApi.get("/system/capabilities");
    window.GenerationCommon.renderCapabilityBanner("capability-banner", caps.image);
  } catch (err) {
    // Non-fatal: generation will still surface a clear error if attempted.
    console.error("[image-generation] Could not load provider capability:", err);
  }
}

async function generateImage() {
  const prompt = document.getElementById("img-prompt").value.trim();
  const projectId = document.getElementById("img-project").value;
  setPromptError("");

  if (!prompt) {
    setPromptError("Describe the image you want.");
    return;
  }

  const aspect = IMG_ASPECTS.find((a) => a.key === selectedAspect) || IMG_ASPECTS[0];
  const btn = document.getElementById("img-generate-btn");
  const originalLabel = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Starting…`;

  try {
    const job = await window.AIAgentApi.post("/generation/image", {
      prompt,
      width: aspect.width,
      height: aspect.height,
      project_id: projectId || undefined,
    });
    renderProgress(job);

    const finalJob = await window.GenerationCommon.pollJob(`/generation/image/${job.id}`, {
      onTick: renderProgress,
    });
    if (finalJob.status === "failed") {
      window.AIAgentToast.show(finalJob.error || "Image generation failed.", "error");
    } else if (finalJob.status === "completed") {
      window.AIAgentToast.show("Image generated.", "success");
    }
    await loadImageJobs();
  } catch (err) {
    if (err.status === 422) {
      const fieldError = (err.fieldErrors || []).find((fe) => fe.field === "prompt");
      setPromptError(fieldError ? fieldError.message : err.message);
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
    user = await window.AppShell.initAppShell("image");
  } catch (err) {
    console.error("[image-generation] Failed to initialize app shell:", err);
    window.AIAgentToast.show("Could not load the application shell. Please refresh the page.", "error");
    return;
  }
  if (!user) return;

  try {
    renderAspectPicker();
    document.getElementById("img-generate-btn").addEventListener("click", generateImage);

    await Promise.all([loadCapability(), window.GenerationCommon.loadProjectOptions("img-project"), loadImageJobs()]);
  } catch (err) {
    console.error("[image-generation] Unexpected error during page initialization:", err);
    window.AIAgentToast.show("Something went wrong loading this page. Please refresh and try again.", "error");
  }
}

init();
