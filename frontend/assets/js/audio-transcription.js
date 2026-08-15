let transcriptionJobs = [];
let selectedAudioBase64 = null;
let selectedFileName = null;

function setFileError(message) {
  const el = document.querySelector('[data-error-for="file"]');
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

function downloadTextAsFile(filename, text) {
  const blob = new Blob([text], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function wireFilePicker() {
  const input = document.getElementById("trans-file");
  input.addEventListener("change", async () => {
    const file = input.files[0];
    if (!file) return;
    setFileError("");
    try {
      selectedAudioBase64 = await fileToBase64(file);
      selectedFileName = file.name;
      document.getElementById("trans-file-name").textContent = `${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
    } catch (err) {
      console.error("[audio-transcription] Could not read audio file:", err);
      window.AIAgentToast.show("Could not read that audio file.", "error");
    }
  });
}

function renderProgress(job) {
  document.getElementById("trans-empty-state").classList.add("d-none");
  const panel = document.getElementById("trans-result-panel");
  panel.style.display = "";
  document.getElementById("trans-result-status").innerHTML = window.GenerationCommon.jobStatusBadge(job.status);

  const body = document.getElementById("trans-result-body");
  if (job.status === "queued" || job.status === "processing") {
    body.innerHTML = `
      <div class="gen-status-row">
        <span class="spinner-border spinner-border-sm"></span> Transcribing your audio…
      </div>
      <div class="gen-progress-track mt-2"><div class="gen-progress-fill indeterminate"></div></div>
    `;
    return;
  }

  if (job.status === "failed") {
    const card = window.GenerationCommon.renderJobErrorCard(job, { onRetry: transcribeAudio });
    body.innerHTML = card.html;
    card.wire();
    return;
  }

  if (job.status === "cancelled") {
    body.innerHTML = `<div class="alert-inline visible">This job was cancelled.</div>`;
    return;
  }

  const text = job.output_metadata.text || "";
  const language = job.output_metadata.language ? ` · Detected language: ${window.GenerationCommon.escapeHtml(job.output_metadata.language)}` : "";
  body.innerHTML = `
    <div class="gen-transcript-text mb-3" id="trans-text-${job.id}">${window.GenerationCommon.escapeHtml(text)}</div>
    <div class="d-flex align-items-center gap-2 flex-wrap">
      <span style="font-size:0.78rem; color:var(--text-muted);">${text.length} characters${language}</span>
      <button type="button" class="btn-ghost ms-auto" style="padding:0.4rem 0.8rem; font-size:0.82rem;" id="trans-copy-btn-${job.id}"><i class="bi bi-clipboard"></i> Copy</button>
      <button type="button" class="btn-brand" style="padding:0.4rem 0.9rem; font-size:0.82rem;" id="trans-download-btn-${job.id}"><i class="bi bi-download"></i> Download .txt</button>
    </div>
  `;

  document.getElementById(`trans-copy-btn-${job.id}`).addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(text);
      window.AIAgentToast.show("Transcript copied.", "success");
    } catch (err) {
      console.error("[audio-transcription] Clipboard write failed:", err);
      window.AIAgentToast.show("Could not copy to clipboard.", "error");
    }
  });
  document.getElementById(`trans-download-btn-${job.id}`).addEventListener("click", () => {
    downloadTextAsFile(`transcript-${job.id}.txt`, text);
  });
}

function renderList() {
  const listEl = document.getElementById("trans-list");
  const emptyEl = document.getElementById("trans-list-empty");
  if (!transcriptionJobs.length) {
    listEl.innerHTML = "";
    emptyEl.classList.remove("d-none");
    return;
  }
  emptyEl.classList.add("d-none");
  listEl.innerHTML = transcriptionJobs
    .map((j) => {
      const preview = (j.output_metadata && j.output_metadata.text) || "Untitled audio";
      return `
    <div class="gen-list-row" data-id="${j.id}">
      <div class="gen-thumb d-flex align-items-center justify-content-center"><i class="bi bi-file-earmark-text" style="color:var(--text-muted);"></i></div>
      <div class="min-width-0 flex-grow-1" style="cursor:pointer;" data-view="${j.id}">
        <div class="gen-title text-truncate">${window.GenerationCommon.escapeHtml(preview)}</div>
        <div class="gen-meta">${window.GenerationCommon.jobStatusBadge(j.status)} · ${window.GenerationCommon.formatDate(j.created_at)}</div>
      </div>
    </div>`;
    })
    .join("");

  listEl.querySelectorAll("[data-view]").forEach((el) => {
    el.addEventListener("click", () => {
      const job = transcriptionJobs.find((j) => j.id === el.dataset.view);
      if (job) renderProgress(job);
    });
  });
}

async function loadTranscriptionJobs() {
  const listEl = document.getElementById("trans-list");
  const emptyEl = document.getElementById("trans-list-empty");
  try {
    transcriptionJobs = await window.AIAgentApi.get("/jobs?type=transcription");
    renderList();
  } catch (err) {
    console.error("[audio-transcription] Could not load recent transcriptions:", err);
    listEl.innerHTML = "";
    emptyEl.classList.remove("d-none");
    emptyEl.querySelector("h6").textContent = "Unable to load recent transcriptions";
    emptyEl.querySelector("p").textContent = err.message || "Please try again.";
    window.AIAgentToast.show("Could not load your recent transcriptions.", "error");
  }
}

async function loadCapability() {
  try {
    const caps = await window.AIAgentApi.get("/system/capabilities");
    window.GenerationCommon.renderCapabilityBanner("capability-banner", caps.transcription);
  } catch (err) {
    console.error("[audio-transcription] Could not load provider capability:", err);
  }
}

async function transcribeAudio() {
  const language = document.getElementById("trans-language").value.trim();
  const projectId = document.getElementById("trans-project").value;
  setFileError("");

  if (!selectedAudioBase64) {
    setFileError("Choose an audio file to transcribe.");
    return;
  }

  const btn = document.getElementById("trans-generate-btn");
  const originalLabel = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Uploading…`;

  try {
    const job = await window.AIAgentApi.post("/generation/audio/transcribe", {
      audio_base64: selectedAudioBase64,
      language: language || undefined,
      project_id: projectId || undefined,
    });
    renderProgress(job);

    const finalJob = await window.GenerationCommon.pollJob(`/generation/audio/transcribe/${job.id}`, {
      onTick: renderProgress,
      timeoutMs: 10 * 60 * 1000,
      intervalMs: 1500,
    });
    if (finalJob.status === "failed") {
      window.AIAgentToast.show(finalJob.error || "Transcription failed.", "error");
    } else if (finalJob.status === "completed") {
      window.AIAgentToast.show("Transcription complete.", "success");
    }
    await loadTranscriptionJobs();
  } catch (err) {
    if (err.status === 422) {
      const fieldError = (err.fieldErrors || []).find((fe) => fe.field === "audio_base64");
      setFileError(fieldError ? fieldError.message : err.message);
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
    user = await window.AppShell.initAppShell("audio-transcription");
  } catch (err) {
    console.error("[audio-transcription] Failed to initialize app shell:", err);
    window.AIAgentToast.show("Could not load the application shell. Please refresh the page.", "error");
    return;
  }
  if (!user) return;

  try {
    wireFilePicker();
    document.getElementById("trans-generate-btn").addEventListener("click", transcribeAudio);

    await Promise.all([loadCapability(), window.GenerationCommon.loadProjectOptions("trans-project"), loadTranscriptionJobs()]);
  } catch (err) {
    console.error("[audio-transcription] Unexpected error during page initialization:", err);
    window.AIAgentToast.show("Something went wrong loading this page. Please refresh and try again.", "error");
  }
}

init();
