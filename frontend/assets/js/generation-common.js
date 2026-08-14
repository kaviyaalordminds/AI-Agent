/* Shared helpers for the Image / Video / Word / PowerPoint / Excel
 * generation pages: escaping, date formatting, status badges, a generic
 * job-status poller (image/video), and project-picker loading. Kept
 * separate from documents.js (which drives the existing AI-drafted
 * Documents Studio) since these pages hit different endpoints
 * (/api/generation/*) but want the same look and feel. */

function genEscapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str == null ? "" : String(str);
  return div.innerHTML;
}

function genFormatDate(iso) {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const JOB_STATUS_BADGES = {
  queued: '<span class="badge-pill badge-muted"><span class="dot dot-muted"></span> Queued</span>',
  processing: '<span class="badge-pill badge-info"><span class="dot dot-muted"></span> Processing</span>',
  completed: '<span class="badge-pill badge-success"><span class="dot dot-success"></span> Completed</span>',
  failed: '<span class="badge-pill badge-danger"><span class="dot dot-danger"></span> Failed</span>',
  cancelled: '<span class="badge-pill badge-muted">Cancelled</span>',
};

function genJobStatusBadge(status) {
  return JOB_STATUS_BADGES[status] || `<span class="badge-pill badge-muted">${genEscapeHtml(status)}</span>`;
}

function genDocStatusBadge(status) {
  return status === "completed"
    ? '<span class="badge-pill badge-success">Completed</span>'
    : '<span class="badge-pill badge-danger">Failed</span>';
}

/* Polls GET `getUrl` every 900ms until the job reaches a terminal status
 * (completed/failed/cancelled), calling onTick with each snapshot so the
 * caller can update a progress UI. Gives up after `timeoutMs` rather than
 * polling forever if something is stuck. Tolerates a few consecutive
 * transient failures (network blip, one slow request) without aborting
 * the whole poll — a real generation can run for minutes, so one bad
 * tick must not surface as a false "generation failed". */
async function genPollJob(getUrl, { onTick, timeoutMs = 120000, intervalMs = 900, maxConsecutiveErrors = 3 } = {}) {
  const deadline = Date.now() + timeoutMs;
  let consecutiveErrors = 0;
  while (Date.now() < deadline) {
    let job;
    try {
      job = await window.AIAgentApi.get(getUrl);
      consecutiveErrors = 0;
    } catch (err) {
      consecutiveErrors += 1;
      console.error(`[generation-common] Poll request failed (attempt ${consecutiveErrors}/${maxConsecutiveErrors}):`, err);
      if (consecutiveErrors >= maxConsecutiveErrors) throw err;
      await new Promise((resolve) => setTimeout(resolve, intervalMs));
      continue;
    }
    if (onTick) onTick(job);
    if (["completed", "failed", "cancelled"].includes(job.status)) return job;
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  throw new Error("This is taking longer than expected. Check back in a moment — it's still running in the background.");
}

async function genLoadProjectOptions(selectId) {
  try {
    const projects = await window.AIAgentApi.get("/projects?status=all");
    const select = document.getElementById(selectId);
    if (!select) return;
    projects.forEach((p) => {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = p.name;
      select.appendChild(opt);
    });
  } catch (err) {
    // Non-fatal: the project picker just stays limited to "No project".
    console.error(`[generation-common] Could not load projects for #${selectId}:`, err);
  }
}

/* Renders a capability banner (used by image/video pages, which depend on
 * an external provider) from a GET /system/capabilities entry. Returns
 * true if the capability is available. */
function genRenderCapabilityBanner(bannerId, capability) {
  const banner = document.getElementById(bannerId);
  if (!banner) return capability.available;
  if (capability.available) {
    banner.classList.add("d-none");
    return true;
  }
  banner.classList.remove("d-none");
  banner.innerHTML = `<i class="bi bi-exclamation-triangle-fill"></i><span>${genEscapeHtml(capability.reason)}</span>`;
  return false;
}

window.GenerationCommon = {
  escapeHtml: genEscapeHtml,
  formatDate: genFormatDate,
  jobStatusBadge: genJobStatusBadge,
  docStatusBadge: genDocStatusBadge,
  pollJob: genPollJob,
  loadProjectOptions: genLoadProjectOptions,
  renderCapabilityBanner: genRenderCapabilityBanner,
};
