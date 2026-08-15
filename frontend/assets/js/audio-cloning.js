let voiceProfiles = [];
let selectedSampleBase64 = null;

function setCloneFieldError(field, message) {
  const el = document.querySelector(`[data-error-for="${field}"]`);
  if (!el) return;
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

function wireFilePicker() {
  const input = document.getElementById("clone-file");
  input.addEventListener("change", async () => {
    const file = input.files[0];
    if (!file) return;
    setCloneFieldError("file", "");
    try {
      selectedSampleBase64 = await fileToBase64(file);
      document.getElementById("clone-file-name").textContent = `${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
    } catch (err) {
      console.error("[audio-cloning] Could not read voice sample file:", err);
      window.AIAgentToast.show("Could not read that audio file.", "error");
    }
  });
}

function renderList() {
  const listEl = document.getElementById("voice-list");
  const emptyEl = document.getElementById("voice-list-empty");
  if (!voiceProfiles.length) {
    listEl.innerHTML = "";
    emptyEl.classList.remove("d-none");
    return;
  }
  emptyEl.classList.add("d-none");
  listEl.innerHTML = voiceProfiles
    .map(
      (v) => `
    <div class="voice-list-row" data-id="${v.id}">
      <div class="min-width-0 flex-grow-1">
        <div class="voice-name text-truncate">${window.GenerationCommon.escapeHtml(v.name)}</div>
        <div class="voice-meta">${window.GenerationCommon.escapeHtml(v.provider)} · ${window.GenerationCommon.formatDate(v.created_at)}</div>
      </div>
      <button type="button" class="btn-ghost" data-delete="${v.id}" aria-label="Delete voice" title="Delete voice" style="color:var(--danger); padding:0.35rem 0.6rem;"><i class="bi bi-trash3"></i></button>
    </div>`
    )
    .join("");

  listEl.querySelectorAll("[data-delete]").forEach((btn) => {
    btn.addEventListener("click", () => deleteVoice(btn.dataset.delete));
  });
}

async function loadVoiceProfiles() {
  const listEl = document.getElementById("voice-list");
  const emptyEl = document.getElementById("voice-list-empty");
  try {
    voiceProfiles = await window.AIAgentApi.get("/generation/audio/voices");
    renderList();
  } catch (err) {
    console.error("[audio-cloning] Could not load cloned voices:", err);
    listEl.innerHTML = "";
    emptyEl.classList.remove("d-none");
    emptyEl.querySelector("h6").textContent = "Unable to load your voices";
    emptyEl.querySelector("p").textContent = err.message || "Please try again.";
    window.AIAgentToast.show("Could not load your cloned voices.", "error");
  }
}

async function loadCapability() {
  try {
    const caps = await window.AIAgentApi.get("/system/capabilities");
    // Voice cloning shares the "voice" capability category with any
    // future voice-related feature — see app/api/system/router.py.
    window.GenerationCommon.renderCapabilityBanner("capability-banner", caps.voice);
  } catch (err) {
    console.error("[audio-cloning] Could not load provider capability:", err);
  }
}

async function deleteVoice(voiceId) {
  const voice = voiceProfiles.find((v) => v.id === voiceId);
  const confirmed = await window.AIAgentModals.confirmAction({
    title: "Delete this voice?",
    message: `"${voice ? voice.name : "This voice"}" will be permanently removed and can no longer be used for Audio Generation.`,
    confirmLabel: "Delete",
    danger: true,
  });
  if (!confirmed) return;

  try {
    await window.AIAgentApi.del(`/generation/audio/voices/${voiceId}`);
    window.AIAgentToast.show("Voice deleted.", "success");
    await loadVoiceProfiles();
  } catch (err) {
    console.error("[audio-cloning] Could not delete voice:", err);
    window.AIAgentToast.show(err.message || "Could not delete this voice.", "error");
  }
}

async function cloneVoice() {
  const name = document.getElementById("clone-name").value.trim();
  const consent = document.getElementById("clone-consent").checked;
  setCloneFieldError("name", "");
  setCloneFieldError("file", "");
  setCloneFieldError("consent", "");

  let hasError = false;
  if (!name) {
    setCloneFieldError("name", "Give the voice a name.");
    hasError = true;
  }
  if (!selectedSampleBase64) {
    setCloneFieldError("file", "Choose a voice sample to clone.");
    hasError = true;
  }
  if (!consent) {
    setCloneFieldError("consent", "You must confirm you have permission to clone this voice.");
    hasError = true;
  }
  if (hasError) return;

  const btn = document.getElementById("clone-create-btn");
  const originalLabel = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Cloning…`;

  try {
    await window.AIAgentApi.post("/generation/audio/voices", {
      name,
      sample_audio_base64: selectedSampleBase64,
      consent_confirmed: consent,
    });
    window.AIAgentToast.show("Voice cloned.", "success");

    document.getElementById("clone-name").value = "";
    document.getElementById("clone-file").value = "";
    document.getElementById("clone-file-name").textContent = "";
    document.getElementById("clone-consent").checked = false;
    selectedSampleBase64 = null;

    await loadVoiceProfiles();
  } catch (err) {
    if (err.status === 422) {
      window.AIAgentToast.show(err.message, "error");
    } else {
      window.AIAgentToast.show(err.message || "Voice cloning failed.", "error");
    }
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalLabel;
  }
}

async function init() {
  let user;
  try {
    user = await window.AppShell.initAppShell("audio-cloning");
  } catch (err) {
    console.error("[audio-cloning] Failed to initialize app shell:", err);
    window.AIAgentToast.show("Could not load the application shell. Please refresh the page.", "error");
    return;
  }
  if (!user) return;

  try {
    wireFilePicker();
    document.getElementById("clone-create-btn").addEventListener("click", cloneVoice);

    await Promise.all([loadCapability(), loadVoiceProfiles()]);
  } catch (err) {
    console.error("[audio-cloning] Unexpected error during page initialization:", err);
    window.AIAgentToast.show("Something went wrong loading this page. Please refresh and try again.", "error");
  }
}

init();
