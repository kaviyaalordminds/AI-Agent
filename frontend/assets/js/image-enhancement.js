const ENHANCEMENT_TYPES = [
  { key: "auto", label: "Auto" },
  { key: "upscale", label: "Upscale" },
  { key: "denoise", label: "Denoise" },
  { key: "color_correction", label: "Color correction" },
  { key: "sharpen", label: "Sharpen" },
  { key: "restore", label: "Restore" },
  { key: "custom", label: "Custom" },
];

let selectedEnhancementType = "auto";
let enhancementJobs = [];
let selectedImageBase64 = null;
let selectedImageDataUrl = null;
let currentEnhancementJobId = null;

function downloadEnhancedUrl(jobId) {
  return `${window.AIAgentApi.apiBase()}/generation/image/enhance/${jobId}/download`;
}

function setFieldError(field, message) {
  const el = document.querySelector(`[data-error-for="${field}"]`);
  if (!el) return;
  el.textContent = message || "";
  el.classList.toggle("visible", Boolean(message));
}

function renderTypePicker() {
  const picker = document.getElementById("enh-type-picker");
  picker.innerHTML = ENHANCEMENT_TYPES.map(
    (t) => `<button type="button" class="mode-pill ${t.key === selectedEnhancementType ? "active" : ""}" data-type="${t.key}">${t.label}</button>`
  ).join("");
  picker.querySelectorAll("[data-type]").forEach((btn) => {
    btn.addEventListener("click", () => {
      selectedEnhancementType = btn.dataset.type;
      renderTypePicker();
      document.getElementById("enh-custom-prompt-wrap").classList.toggle("d-none", selectedEnhancementType !== "custom");
    });
  });
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

async function handleSelectedFile(file) {
  if (!file) return;
  setFieldError("file", "");
  if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) {
    setFieldError("file", "Please choose a PNG, JPEG, or WEBP image.");
    return;
  }
  try {
    const dataUrl = await fileToBase64(file);
    selectedImageDataUrl = dataUrl;
    selectedImageBase64 = dataUrl.split(",")[1];
    document.getElementById("enh-file-name").textContent = `${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
    const frame = document.getElementById("enh-source-preview-frame");
    const img = document.getElementById("enh-source-preview-img");
    img.src = dataUrl;
    frame.classList.remove("d-none");
  } catch (err) {
    console.error("[image-enhancement] Could not read image file:", err);
    window.AIAgentToast.show("Could not read that image file.", "error");
  }
}

function wireUpload() {
  const dropzone = document.getElementById("enh-dropzone");
  const input = document.getElementById("enh-file");

  input.addEventListener("change", () => handleSelectedFile(input.files[0]));

  ["dragenter", "dragover"].forEach((evt) => {
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.add("dragover");
    });
  });
  ["dragleave", "drop"].forEach((evt) => {
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.remove("dragover");
    });
  });
  dropzone.addEventListener("drop", (e) => {
    const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
    if (file) handleSelectedFile(file);
  });
}

function renderProgress(job) {
  document.getElementById("enh-empty-state").classList.add("d-none");
  const panel = document.getElementById("enh-result-panel");
  panel.style.display = "";
  document.getElementById("enh-result-status").innerHTML = window.GenerationCommon.jobStatusBadge(job.status);

  const body = document.getElementById("enh-result-body");
  if (job.status === "queued" || job.status === "processing") {
    body.innerHTML = `
      <div class="gen-preview-frame mb-3">
        <div class="text-center">
          <span class="spinner-border spinner-border-sm mb-2"></span>
          <div class="gen-status-row justify-content-center">Enhancing your image…</div>
        </div>
      </div>
      <div class="gen-progress-track"><div class="gen-progress-fill indeterminate"></div></div>
    `;
    return;
  }

  if (job.status === "failed") {
    const card = window.GenerationCommon.renderJobErrorCard(job, { providerLabel: "OpenAI", onRetry: enhanceImage });
    body.innerHTML = card.html;
    card.wire();
    return;
  }

  if (job.status === "cancelled") {
    body.innerHTML = `<div class="alert-inline visible">This job was cancelled.</div>`;
    return;
  }

  const sourcePreview = job.id === currentEnhancementJobId ? selectedImageDataUrl : null;
  body.innerHTML = `
    <div class="enhance-compare mb-3">
      ${sourcePreview ? `
      <div class="enhance-compare-col">
        <span class="enhance-compare-label">Before</span>
        <div class="gen-preview-frame"><img src="${sourcePreview}" alt="Original image"></div>
      </div>` : ""}
      <div class="enhance-compare-col">
        <span class="enhance-compare-label">After</span>
        <div class="gen-preview-frame"><img src="${downloadEnhancedUrl(job.id)}" alt="Enhanced image"></div>
      </div>
    </div>
    <div class="d-flex align-items-center gap-2">
      <span style="font-size:0.78rem; color:var(--text-muted);">${job.output_metadata.size_bytes ? `${(job.output_metadata.size_bytes / 1024).toFixed(1)} KB` : ""}</span>
      <a class="btn-brand ms-auto" style="padding:0.4rem 0.9rem; font-size:0.82rem;" href="${downloadEnhancedUrl(job.id)}" target="_blank" rel="noopener"><i class="bi bi-download"></i> Download</a>
    </div>
  `;
}

function renderList() {
  const listEl = document.getElementById("enh-list");
  const emptyEl = document.getElementById("enh-list-empty");
  if (!enhancementJobs.length) {
    listEl.innerHTML = "";
    emptyEl.classList.remove("d-none");
    return;
  }
  emptyEl.classList.add("d-none");
  listEl.innerHTML = enhancementJobs
    .map(
      (j) => `
    <div class="gen-list-row" data-id="${j.id}">
      ${j.status === "completed" ? `<img class="gen-thumb" src="${downloadEnhancedUrl(j.id)}" alt="" />` : `<div class="gen-thumb d-flex align-items-center justify-content-center"><i class="bi bi-magic" style="color:var(--text-muted);"></i></div>`}
      <div class="min-width-0 flex-grow-1" style="cursor:pointer;" data-view="${j.id}">
        <div class="gen-title text-truncate">${window.GenerationCommon.escapeHtml((j.input_metadata && j.input_metadata.enhancement_type) || "Enhancement")}</div>
        <div class="gen-meta">${window.GenerationCommon.jobStatusBadge(j.status)} · ${window.GenerationCommon.formatDate(j.created_at)}</div>
      </div>
      <div class="gen-actions">
        ${j.status === "completed" ? `<a class="btn-ghost" style="padding:0.35rem 0.6rem;" href="${downloadEnhancedUrl(j.id)}" target="_blank" rel="noopener" title="Download"><i class="bi bi-download"></i></a>` : ""}
      </div>
    </div>`
    )
    .join("");

  listEl.querySelectorAll("[data-view]").forEach((el) => {
    el.addEventListener("click", () => {
      const job = enhancementJobs.find((j) => j.id === el.dataset.view);
      if (job) {
        if (job.id !== currentEnhancementJobId) currentEnhancementJobId = null;
        renderProgress(job);
      }
    });
  });
}

async function loadEnhancementJobs() {
  const listEl = document.getElementById("enh-list");
  const emptyEl = document.getElementById("enh-list-empty");
  try {
    enhancementJobs = await window.AIAgentApi.get("/jobs?type=image_enhancement");
    renderList();
  } catch (err) {
    console.error("[image-enhancement] Could not load recent enhancements:", err);
    listEl.innerHTML = "";
    emptyEl.classList.remove("d-none");
    emptyEl.querySelector("h6").textContent = "Unable to load recent generations";
    emptyEl.querySelector("p").textContent = err.message || "Please try again.";
    window.AIAgentToast.show("Could not load your recent enhancements.", "error");
  }
}

async function loadCapability() {
  try {
    const caps = await window.AIAgentApi.get("/system/capabilities");
    window.GenerationCommon.renderCapabilityBanner("capability-banner", caps.image);
  } catch (err) {
    console.error("[image-enhancement] Could not load provider capability:", err);
  }
}

async function enhanceImage() {
  const projectId = document.getElementById("enh-project").value;
  const prompt = document.getElementById("enh-prompt").value.trim();
  setFieldError("file", "");
  setFieldError("prompt", "");

  if (!selectedImageBase64) {
    setFieldError("file", "Choose an image to enhance.");
    return;
  }
  if (selectedEnhancementType === "custom" && !prompt) {
    setFieldError("prompt", "Describe how you want this image enhanced.");
    return;
  }

  const btn = document.getElementById("enh-generate-btn");
  const originalLabel = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Starting…`;

  try {
    const job = await window.AIAgentApi.post("/generation/image/enhance", {
      image_base64: selectedImageBase64,
      enhancement_type: selectedEnhancementType,
      prompt: prompt || undefined,
      project_id: projectId || undefined,
    });
    currentEnhancementJobId = job.id;
    renderProgress(job);

    const finalJob = await window.GenerationCommon.pollJob(`/generation/image/enhance/${job.id}`, {
      onTick: renderProgress,
    });
    if (finalJob.status === "failed") {
      window.AIAgentToast.show(finalJob.error || "Image enhancement failed.", "error");
    } else if (finalJob.status === "completed") {
      window.AIAgentToast.show("Image enhanced.", "success");
    }
    await loadEnhancementJobs();
  } catch (err) {
    if (err.status === 422) {
      const fieldError = (err.fieldErrors || []).find((fe) => fe.field === "image_base64" || fe.field === "prompt");
      if (fieldError) {
        setFieldError(fieldError.field === "image_base64" ? "file" : "prompt", fieldError.message);
      } else {
        window.AIAgentToast.show(err.message, "error");
      }
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
    user = await window.AppShell.initAppShell("image-enhancement");
  } catch (err) {
    console.error("[image-enhancement] Failed to initialize app shell:", err);
    window.AIAgentToast.show("Could not load the application shell. Please refresh the page.", "error");
    return;
  }
  if (!user) return;

  try {
    renderTypePicker();
    wireUpload();
    document.getElementById("enh-generate-btn").addEventListener("click", enhanceImage);

    await Promise.all([loadCapability(), window.GenerationCommon.loadProjectOptions("enh-project"), loadEnhancementJobs()]);
  } catch (err) {
    console.error("[image-enhancement] Unexpected error during page initialization:", err);
    window.AIAgentToast.show("Something went wrong loading this page. Please refresh and try again.", "error");
  }
}

init();
