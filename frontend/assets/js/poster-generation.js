const POS_ASPECTS = [
  { key: "1:1", label: "Square", width: 1024, height: 1024, w: 22, h: 22 },
  { key: "3:4", label: "Portrait", width: 896, height: 1152, w: 17, h: 22 },
  { key: "4:3", label: "Landscape", width: 1152, height: 896, w: 22, h: 17 },
  { key: "9:16", label: "Story", width: 768, height: 1344, w: 13, h: 22 },
];

let selectedPosAspect = "3:4";
let posterJobs = [];

function downloadPosterUrl(id) {
  return `${window.AIAgentApi.apiBase()}/generation/poster/${id}/download`;
}

function renderPosAspectPicker() {
  const picker = document.getElementById("pos-aspect-picker");
  picker.innerHTML = POS_ASPECTS.map(
    (a) => `
    <button type="button" class="aspect-pill ${a.key === selectedPosAspect ? "active" : ""}" data-aspect="${a.key}">
      <span class="aspect-swatch" style="width:${a.w}px; height:${a.h}px;"></span>
      ${a.label}
    </button>`
  ).join("");
  picker.querySelectorAll("[data-aspect]").forEach((btn) => {
    btn.addEventListener("click", () => {
      selectedPosAspect = btn.dataset.aspect;
      renderPosAspectPicker();
    });
  });
}

function setPosError(field, message) {
  const el = document.querySelector(`[data-error-for="${field}"]`);
  el.textContent = message || "";
  el.classList.toggle("visible", Boolean(message));
}

function renderPosProgress(job) {
  document.getElementById("pos-empty-state").classList.add("d-none");
  const panel = document.getElementById("pos-result-panel");
  panel.style.display = "";
  document.getElementById("pos-result-status").innerHTML = window.GenerationCommon.jobStatusBadge(job.status);

  const body = document.getElementById("pos-result-body");
  if (job.status === "queued" || job.status === "processing") {
    body.innerHTML = `
      <div class="gen-preview-frame mb-3">
        <div class="text-center">
          <span class="spinner-border spinner-border-sm mb-2"></span>
          <div class="gen-status-row justify-content-center">Generating your poster…</div>
        </div>
      </div>
      <div class="gen-progress-track"><div class="gen-progress-fill indeterminate"></div></div>
    `;
    return;
  }

  if (job.status === "failed") {
    const card = window.GenerationCommon.renderJobErrorCard(job, { providerLabel: "OpenAI", onRetry: generatePoster });
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
      <img src="${downloadPosterUrl(job.id)}" alt="Generated poster" />
    </div>
    <div class="d-flex align-items-center gap-2">
      <span style="font-size:0.78rem; color:var(--text-muted);">${job.output_metadata.size_bytes ? `${(job.output_metadata.size_bytes / 1024).toFixed(1)} KB` : ""}</span>
      <a class="btn-brand ms-auto" style="padding:0.4rem 0.9rem; font-size:0.82rem;" href="${downloadPosterUrl(job.id)}" target="_blank" rel="noopener"><i class="bi bi-download"></i> Download</a>
    </div>
  `;
}

function renderPosList() {
  const listEl = document.getElementById("pos-list");
  const emptyEl = document.getElementById("pos-list-empty");
  emptyEl.querySelector("h6").textContent = "No posters yet";
  emptyEl.querySelector("p").textContent = "Posters you generate will be listed here.";
  if (!posterJobs.length) {
    listEl.innerHTML = "";
    emptyEl.classList.remove("d-none");
    return;
  }
  emptyEl.classList.add("d-none");
  listEl.innerHTML = posterJobs
    .map(
      (j) => `
    <div class="gen-list-row" data-id="${j.id}">
      ${j.status === "completed" ? `<img class="gen-thumb" src="${downloadPosterUrl(j.id)}" alt="" />` : `<div class="gen-thumb d-flex align-items-center justify-content-center"><i class="bi bi-file-earmark-image" style="color:var(--text-muted);"></i></div>`}
      <div class="min-width-0 flex-grow-1" style="cursor:pointer;" data-view="${j.id}">
        <div class="gen-title text-truncate">${window.GenerationCommon.escapeHtml((j.input_metadata && j.input_metadata.headline) || "Untitled poster")}</div>
        <div class="gen-meta">${window.GenerationCommon.jobStatusBadge(j.status)} · ${window.GenerationCommon.formatDate(j.created_at)}</div>
      </div>
      <div class="gen-actions">
        ${j.status === "completed" ? `<a class="btn-ghost" style="padding:0.35rem 0.6rem;" href="${downloadPosterUrl(j.id)}" target="_blank" rel="noopener" title="Download"><i class="bi bi-download"></i></a>` : ""}
      </div>
    </div>`
    )
    .join("");

  listEl.querySelectorAll("[data-view]").forEach((el) => {
    el.addEventListener("click", () => {
      const job = posterJobs.find((j) => j.id === el.dataset.view);
      if (job) renderPosProgress(job);
    });
  });
}

async function loadPosterJobs() {
  const listEl = document.getElementById("pos-list");
  const emptyEl = document.getElementById("pos-list-empty");
  try {
    posterJobs = await window.AIAgentApi.get("/jobs?type=poster");
    renderPosList();
  } catch (err) {
    console.error("[poster-generation] Could not load recent generations:", err);
    listEl.innerHTML = "";
    emptyEl.classList.remove("d-none");
    emptyEl.querySelector("h6").textContent = "Unable to load recent generations";
    emptyEl.querySelector("p").textContent = err.message || "Please try again.";
    window.AIAgentToast.show("Could not load your recent posters.", "error");
  }
}

async function loadPosCapability() {
  try {
    const caps = await window.AIAgentApi.get("/system/capabilities");
    window.GenerationCommon.renderCapabilityBanner("capability-banner", caps.image);
  } catch (err) {
    console.error("[poster-generation] Could not load provider capability:", err);
  }
}

async function generatePoster() {
  const headline = document.getElementById("pos-headline").value.trim();
  const subheading = document.getElementById("pos-subheading").value.trim();
  const prompt = document.getElementById("pos-prompt").value.trim();
  const projectId = document.getElementById("pos-project").value;
  setPosError("headline", "");
  setPosError("prompt", "");

  let hasError = false;
  if (!headline) {
    setPosError("headline", "Give the poster a headline.");
    hasError = true;
  }
  if (!prompt) {
    setPosError("prompt", "Describe the visual style you want.");
    hasError = true;
  }
  if (hasError) return;

  const aspect = POS_ASPECTS.find((a) => a.key === selectedPosAspect) || POS_ASPECTS[0];
  const btn = document.getElementById("pos-generate-btn");
  const originalLabel = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Starting…`;

  try {
    const job = await window.AIAgentApi.post("/generation/poster", {
      headline,
      subheading: subheading || undefined,
      prompt,
      width: aspect.width,
      height: aspect.height,
      project_id: projectId || undefined,
    });
    renderPosProgress(job);

    const finalJob = await window.GenerationCommon.pollJob(`/generation/poster/${job.id}`, {
      onTick: renderPosProgress,
    });
    if (finalJob.status === "failed") {
      window.AIAgentToast.show(finalJob.error || "Poster generation failed.", "error");
    } else if (finalJob.status === "completed") {
      window.AIAgentToast.show("Poster generated.", "success");
    }
    await loadPosterJobs();
  } catch (err) {
    if (err.status === 422) {
      const fieldError = (err.fieldErrors || []).find((fe) => fe.field === "headline" || fe.field === "prompt");
      if (fieldError) setPosError(fieldError.field, fieldError.message);
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
    user = await window.AppShell.initAppShell("poster");
  } catch (err) {
    console.error("[poster-generation] Failed to initialize app shell:", err);
    window.AIAgentToast.show("Could not load the application shell. Please refresh the page.", "error");
    return;
  }
  if (!user) return;

  try {
    renderPosAspectPicker();
    document.getElementById("pos-generate-btn").addEventListener("click", generatePoster);

    await Promise.all([loadPosCapability(), window.GenerationCommon.loadProjectOptions("pos-project"), loadPosterJobs()]);
  } catch (err) {
    console.error("[poster-generation] Unexpected error during page initialization:", err);
    window.AIAgentToast.show("Something went wrong loading this page. Please refresh and try again.", "error");
  }
}

init();
