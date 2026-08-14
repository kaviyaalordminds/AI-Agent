const CAPABILITY_ICONS = {
  ai: "bi-cpu",
  audio: "bi-mic",
  transcription: "bi-file-earmark-music",
  voice: "bi-soundwave",
  image: "bi-image",
  video: "bi-camera-reels",
  documents: "bi-file-earmark-text",
  obsidian: "bi-safe2",
  storage: "bi-hdd",
  deployment: "bi-cloud-arrow-up",
};

const CAPABILITY_LABELS = {
  ai: "AI",
  audio: "Audio (TTS)",
  transcription: "Transcription",
  voice: "Voice Cloning",
  image: "Image",
  video: "Video",
  documents: "Documents",
  obsidian: "Obsidian / Knowledge",
  storage: "Storage",
  deployment: "Deployment",
};

const HEALTH_LABELS = {
  database: "Database",
  ai_provider: "AI Provider",
  obsidian: "Obsidian",
  storage: "Storage",
  job_queue: "Job Queue",
};

function sysEscapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function renderCapabilityGrid(containerId, capabilities) {
  const container = document.getElementById(containerId);
  if (!container) return;
  container.innerHTML = Object.entries(capabilities)
    .map(([key, cap]) => {
      const badgeClass = cap.available ? "badge-success" : "badge-muted";
      const dotClass = cap.available ? "dot-success" : "dot-muted";
      return `
      <div class="surface capability-card">
        <div class="cap-header">
          <span class="cap-name"><i class="bi ${CAPABILITY_ICONS[key] || "bi-puzzle"}"></i> ${CAPABILITY_LABELS[key] || key}</span>
          <span class="badge-pill ${badgeClass}"><span class="dot ${dotClass}"></span> ${cap.available ? "Available" : "Unavailable"}</span>
        </div>
        <div class="cap-meta">${sysEscapeHtml(cap.provider)} &middot; ${cap.mode}</div>
        <div class="cap-reason">${sysEscapeHtml(cap.reason)}</div>
      </div>`;
    })
    .join("");
}

function renderHealthList(containerId, health) {
  const container = document.getElementById(containerId);
  if (!container) return;
  const badgeForStatus = { ok: "badge-success", degraded: "badge-warning", down: "badge-danger" };
  const dotForStatus = { ok: "dot-success", degraded: "dot-muted", down: "dot-danger" };
  container.innerHTML = Object.entries(health)
    .map(
      ([key, comp]) => `
    <div class="health-row">
      <div>
        <div class="health-name">${HEALTH_LABELS[key] || key}</div>
        <div class="health-detail">${sysEscapeHtml(comp.detail)}</div>
      </div>
      <span class="badge-pill ${badgeForStatus[comp.status] || "badge-muted"}"><span class="dot ${dotForStatus[comp.status] || "dot-muted"}"></span> ${comp.status}</span>
    </div>`
    )
    .join("");
}

async function loadSystemStatus(capabilityContainerId, healthContainerId) {
  try {
    const [capabilities, health] = await Promise.all([
      window.AIAgentApi.get("/system/capabilities"),
      window.AIAgentApi.get("/system/providers/health"),
    ]);
    renderCapabilityGrid(capabilityContainerId, capabilities);
    renderHealthList(healthContainerId, health);
  } catch (err) {
    window.AIAgentToast.show(err.message || "Could not load system status.", "error");
  }
}

window.SystemStatus = { loadSystemStatus, renderCapabilityGrid, renderHealthList };
