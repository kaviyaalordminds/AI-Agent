let audioJobs = [];

function downloadAudioUrl(id) {
  return `${window.AIAgentApi.apiBase()}/jobs/${id}/download`;
}

function setTextError(message) {
  const el = document.querySelector('[data-error-for="text"]');
  el.textContent = message || "";
  el.classList.toggle("visible", Boolean(message));
}

function renderProgress(job) {
  document.getElementById("aud-empty-state").classList.add("d-none");
  const panel = document.getElementById("aud-result-panel");
  panel.style.display = "";
  document.getElementById("aud-result-status").innerHTML = window.GenerationCommon.jobStatusBadge(job.status);

  const body = document.getElementById("aud-result-body");
  if (job.status === "queued" || job.status === "processing") {
    body.innerHTML = `
      <div class="gen-preview-frame mb-3">
        <div class="text-center">
          <span class="spinner-border spinner-border-sm mb-2"></span>
          <div class="gen-status-row justify-content-center">Generating your audio…</div>
        </div>
      </div>
      <div class="gen-progress-track"><div class="gen-progress-fill indeterminate"></div></div>
    `;
    return;
  }

  if (job.status === "failed") {
    const card = window.GenerationCommon.renderJobErrorCard(job, { onRetry: generateAudio });
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
      <audio src="${downloadAudioUrl(job.id)}" controls></audio>
    </div>
    <div class="d-flex align-items-center gap-2">
      <span style="font-size:0.78rem; color:var(--text-muted);">${job.output_metadata.size_bytes ? `${(job.output_metadata.size_bytes / 1024).toFixed(1)} KB` : ""}</span>
      <a class="btn-brand ms-auto" style="padding:0.4rem 0.9rem; font-size:0.82rem;" href="${downloadAudioUrl(job.id)}" target="_blank" rel="noopener"><i class="bi bi-download"></i> Download</a>
    </div>
  `;
}

function renderList() {
  const listEl = document.getElementById("aud-list");
  const emptyEl = document.getElementById("aud-list-empty");
  if (!audioJobs.length) {
    listEl.innerHTML = "";
    emptyEl.classList.remove("d-none");
    return;
  }
  emptyEl.classList.add("d-none");
  listEl.innerHTML = audioJobs
    .map(
      (j) => `
    <div class="gen-list-row" data-id="${j.id}">
      <div class="gen-thumb d-flex align-items-center justify-content-center"><i class="bi bi-mic" style="color:var(--text-muted);"></i></div>
      <div class="min-width-0 flex-grow-1" style="cursor:pointer;" data-view="${j.id}">
        <div class="gen-title text-truncate">${window.GenerationCommon.escapeHtml((j.input_metadata && j.input_metadata.text) || "Untitled script")}</div>
        <div class="gen-meta">${window.GenerationCommon.jobStatusBadge(j.status)} · ${window.GenerationCommon.formatDate(j.created_at)}</div>
      </div>
      <div class="gen-actions">
        ${j.status === "completed" ? `<a class="btn-ghost" style="padding:0.35rem 0.6rem;" href="${downloadAudioUrl(j.id)}" target="_blank" rel="noopener" title="Download"><i class="bi bi-download"></i></a>` : ""}
      </div>
    </div>`
    )
    .join("");

  listEl.querySelectorAll("[data-view]").forEach((el) => {
    el.addEventListener("click", () => {
      const job = audioJobs.find((j) => j.id === el.dataset.view);
      if (job) renderProgress(job);
    });
  });
}

async function loadAudioJobs() {
  const listEl = document.getElementById("aud-list");
  const emptyEl = document.getElementById("aud-list-empty");
  try {
    audioJobs = await window.AIAgentApi.get("/jobs?type=audio");
    renderList();
  } catch (err) {
    console.error("[audio-generation] Could not load recent generations:", err);
    listEl.innerHTML = "";
    emptyEl.classList.remove("d-none");
    emptyEl.querySelector("h6").textContent = "Unable to load recent generations";
    emptyEl.querySelector("p").textContent = err.message || "Please try again.";
    window.AIAgentToast.show("Could not load your recent audio.", "error");
  }
}

async function loadCapability() {
  try {
    const caps = await window.AIAgentApi.get("/system/capabilities");
    window.GenerationCommon.renderCapabilityBanner("capability-banner", caps.audio);
  } catch (err) {
    console.error("[audio-generation] Could not load provider capability:", err);
  }
}

async function loadVoiceOptions() {
  const select = document.getElementById("aud-voice");
  try {
    const voices = await window.AIAgentApi.get("/generation/audio/voices");
    voices.forEach((v) => {
      const opt = document.createElement("option");
      opt.value = `profile:${v.id}`;
      opt.textContent = `${v.name} (cloned)`;
      select.appendChild(opt);
    });
  } catch (err) {
    // Non-fatal: the voice picker just stays limited to the default voice.
    console.error("[audio-generation] Could not load cloned voices:", err);
  }
}

async function generateAudio() {
  const text = document.getElementById("aud-text").value.trim();
  const speed = Number(document.getElementById("aud-speed").value);
  const voiceValue = document.getElementById("aud-voice").value;
  const projectId = document.getElementById("aud-project").value;
  setTextError("");

  if (!text) {
    setTextError("Write the script you want narrated.");
    return;
  }

  const btn = document.getElementById("aud-generate-btn");
  const originalLabel = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Starting…`;

  const isClonedVoice = voiceValue.startsWith("profile:");

  try {
    const job = await window.AIAgentApi.post("/jobs/audio", {
      text,
      speed,
      voice: isClonedVoice ? undefined : voiceValue || undefined,
      voice_profile_id: isClonedVoice ? voiceValue.slice("profile:".length) : undefined,
      project_id: projectId || undefined,
    });
    renderProgress(job);

    const finalJob = await window.GenerationCommon.pollJob(`/jobs/${job.id}`, {
      onTick: renderProgress,
      timeoutMs: 5 * 60 * 1000,
      intervalMs: 1200,
    });
    if (finalJob.status === "failed") {
      window.AIAgentToast.show(finalJob.error || "Audio generation failed.", "error");
    } else if (finalJob.status === "completed") {
      window.AIAgentToast.show("Audio generated.", "success");
    }
    await loadAudioJobs();
  } catch (err) {
    if (err.status === 422) {
      const fieldError = (err.fieldErrors || []).find((fe) => fe.field === "text");
      setTextError(fieldError ? fieldError.message : err.message);
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
    user = await window.AppShell.initAppShell("audio-generation");
  } catch (err) {
    console.error("[audio-generation] Failed to initialize app shell:", err);
    window.AIAgentToast.show("Could not load the application shell. Please refresh the page.", "error");
    return;
  }
  if (!user) return;

  try {
    document.getElementById("aud-speed").addEventListener("input", (e) => {
      document.getElementById("aud-speed-value").textContent = Number(e.target.value).toFixed(1);
    });
    document.getElementById("aud-generate-btn").addEventListener("click", generateAudio);

    await Promise.all([
      loadCapability(),
      loadVoiceOptions(),
      window.GenerationCommon.loadProjectOptions("aud-project"),
      loadAudioJobs(),
    ]);
  } catch (err) {
    console.error("[audio-generation] Unexpected error during page initialization:", err);
    window.AIAgentToast.show("Something went wrong loading this page. Please refresh and try again.", "error");
  }
}

init();
