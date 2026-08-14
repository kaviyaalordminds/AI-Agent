let videoJobs = [];
let referenceImageBase64 = null;

function downloadVideoUrl(id) {
  return `${window.AIAgentApi.apiBase()}/generation/video/${id}/download`;
}

function setPromptError(message) {
  const el = document.querySelector('[data-error-for="prompt"]');
  el.textContent = message || "";
  el.classList.toggle("visible", Boolean(message));
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(",")[1]);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function wireReferenceImagePicker() {
  const input = document.getElementById("vid-reference-image");
  const preview = document.getElementById("vid-reference-preview");
  const previewImg = document.getElementById("vid-reference-preview-img");
  const clearBtn = document.getElementById("vid-reference-clear");

  input.addEventListener("change", async () => {
    const file = input.files[0];
    if (!file) return;
    try {
      referenceImageBase64 = await fileToBase64(file);
      previewImg.src = `data:${file.type};base64,${referenceImageBase64}`;
      preview.classList.remove("d-none");
    } catch {
      window.AIAgentToast.show("Could not read that image file.", "error");
    }
  });

  clearBtn.addEventListener("click", () => {
    referenceImageBase64 = null;
    input.value = "";
    preview.classList.add("d-none");
  });
}

function renderProgress(job) {
  document.getElementById("vid-empty-state").classList.add("d-none");
  const panel = document.getElementById("vid-result-panel");
  panel.style.display = "";
  document.getElementById("vid-result-status").innerHTML = window.GenerationCommon.jobStatusBadge(job.status);

  const body = document.getElementById("vid-result-body");
  if (job.status === "queued" || job.status === "processing") {
    body.innerHTML = `
      <div class="gen-preview-frame mb-3">
        <div class="text-center">
          <span class="spinner-border spinner-border-sm mb-2"></span>
          <div class="gen-status-row justify-content-center">Generating your video — this can take a minute or more…</div>
        </div>
      </div>
      <div class="gen-progress-track"><div class="gen-progress-fill indeterminate"></div></div>
    `;
    return;
  }

  if (job.status === "failed") {
    body.innerHTML = `<div class="alert-inline visible error">${window.GenerationCommon.escapeHtml(job.error || "Video generation failed.")}</div>`;
    return;
  }

  if (job.status === "cancelled") {
    body.innerHTML = `<div class="alert-inline visible">This job was cancelled.</div>`;
    return;
  }

  body.innerHTML = `
    <div class="gen-preview-frame mb-3">
      <video src="${downloadVideoUrl(job.id)}" controls></video>
    </div>
    <div class="d-flex align-items-center gap-2">
      <span style="font-size:0.78rem; color:var(--text-muted);">${job.output_metadata.size_bytes ? `${(job.output_metadata.size_bytes / 1024 / 1024).toFixed(2)} MB` : ""}</span>
      <a class="btn-brand ms-auto" style="padding:0.4rem 0.9rem; font-size:0.82rem;" href="${downloadVideoUrl(job.id)}" target="_blank" rel="noopener"><i class="bi bi-download"></i> Download</a>
    </div>
  `;
}

function renderList() {
  const listEl = document.getElementById("vid-list");
  const emptyEl = document.getElementById("vid-list-empty");
  if (!videoJobs.length) {
    listEl.innerHTML = "";
    emptyEl.classList.remove("d-none");
    return;
  }
  emptyEl.classList.add("d-none");
  listEl.innerHTML = videoJobs
    .map(
      (j) => `
    <div class="gen-list-row" data-id="${j.id}">
      <div class="gen-thumb d-flex align-items-center justify-content-center"><i class="bi bi-camera-reels" style="color:var(--text-muted);"></i></div>
      <div class="min-width-0 flex-grow-1" style="cursor:pointer;" data-view="${j.id}">
        <div class="gen-title text-truncate">${window.GenerationCommon.escapeHtml((j.input_metadata && j.input_metadata.prompt) || "Untitled prompt")}</div>
        <div class="gen-meta">${window.GenerationCommon.jobStatusBadge(j.status)} · ${window.GenerationCommon.formatDate(j.created_at)}</div>
      </div>
      <div class="gen-actions">
        ${j.status === "completed" ? `<a class="btn-ghost" style="padding:0.35rem 0.6rem;" href="${downloadVideoUrl(j.id)}" target="_blank" rel="noopener" title="Download"><i class="bi bi-download"></i></a>` : ""}
      </div>
    </div>`
    )
    .join("");

  listEl.querySelectorAll("[data-view]").forEach((el) => {
    el.addEventListener("click", () => {
      const job = videoJobs.find((j) => j.id === el.dataset.view);
      if (job) renderProgress(job);
    });
  });
}

async function loadVideoJobs() {
  try {
    videoJobs = await window.AIAgentApi.get("/jobs?type=video");
    renderList();
  } catch {
    window.AIAgentToast.show("Could not load your recent videos.", "error");
  }
}

async function loadCapability() {
  try {
    const caps = await window.AIAgentApi.get("/system/capabilities");
    window.GenerationCommon.renderCapabilityBanner("capability-banner", caps.video);
  } catch {
    // Non-fatal: generation will still surface a clear error if attempted.
  }
}

async function generateVideo() {
  const prompt = document.getElementById("vid-prompt").value.trim();
  const duration = Number(document.getElementById("vid-duration").value);
  const projectId = document.getElementById("vid-project").value;
  setPromptError("");

  if (!prompt) {
    setPromptError("Describe the video you want.");
    return;
  }

  const btn = document.getElementById("vid-generate-btn");
  const originalLabel = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Starting…`;

  try {
    const job = await window.AIAgentApi.post("/generation/video", {
      prompt,
      duration_seconds: duration,
      reference_image_base64: referenceImageBase64 || undefined,
      project_id: projectId || undefined,
    });
    renderProgress(job);

    const finalJob = await window.GenerationCommon.pollJob(`/generation/video/${job.id}`, {
      onTick: renderProgress,
      timeoutMs: 15 * 60 * 1000,
      intervalMs: 2500,
    });
    if (finalJob.status === "failed") {
      window.AIAgentToast.show(finalJob.error || "Video generation failed.", "error");
    } else if (finalJob.status === "completed") {
      window.AIAgentToast.show("Video generated.", "success");
    }
    await loadVideoJobs();
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
  const user = await window.AppShell.initAppShell("video");
  if (!user) return;

  wireReferenceImagePicker();
  document.getElementById("vid-duration").addEventListener("input", (e) => {
    document.getElementById("vid-duration-value").textContent = e.target.value;
  });
  document.getElementById("vid-generate-btn").addEventListener("click", generateVideo);

  await Promise.all([loadCapability(), window.GenerationCommon.loadProjectOptions("vid-project"), loadVideoJobs()]);
}

init();
