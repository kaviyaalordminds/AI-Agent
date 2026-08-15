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

/* A failed GenerationJob carries a structured `error_type` (see
 * backend app/integrations/generation/errors.py) so this card can show
 * the actual cloud-provider problem — quota exhausted, bad/revoked
 * credential, vendor outage, or not configured — instead of one generic
 * "generation failed" message for every case. */
const GEN_ERROR_TYPE_META = {
  quota_exceeded: { icon: "bi-hourglass-bottom", title: "Quota exceeded" },
  auth_error: { icon: "bi-key-fill", title: "Authentication error" },
  provider_unavailable: { icon: "bi-cloud-slash", title: "Provider unavailable" },
  not_configured: { icon: "bi-gear-fill", title: "Not configured" },
};

/* Renders a failed job as a professional error card: provider name,
 * a title specific to what actually went wrong, the real (non-secret)
 * message from the provider, and — unless the failure is "not
 * configured" (nothing to retry until an admin sets a key) — a Retry
 * button wired to `onRetry`. Never clears the surrounding page and never
 * touches auth/session state; a generation failure is never a reason to
 * redirect to login. */
function genRenderJobErrorCard(job, { providerLabel, onRetry } = {}) {
  const meta = GEN_ERROR_TYPE_META[job.error_type] || { icon: "bi-exclamation-triangle-fill", title: "Generation failed" };
  const titleSuffix = providerLabel ? ` — ${genEscapeHtml(providerLabel)}` : "";
  const showRetry = Boolean(onRetry) && job.error_type !== "not_configured";
  const retryBtnId = `gen-error-retry-${Math.random().toString(36).slice(2, 8)}`;

  const html = `
    <div class="gen-error-card">
      <div class="gen-error-icon"><i class="bi ${meta.icon}"></i></div>
      <div class="gen-error-body">
        <div class="gen-error-title">${meta.title}${titleSuffix}</div>
        <div class="gen-error-message">${genEscapeHtml(job.error || "Generation failed.")}</div>
        ${showRetry ? `<button type="button" class="btn-brand gen-error-retry-btn" id="${retryBtnId}" style="margin-top:0.75rem; padding:0.4rem 0.9rem; font-size:0.82rem;"><i class="bi bi-arrow-clockwise"></i> Retry</button>` : ""}
      </div>
    </div>`;

  return {
    html,
    wire() {
      if (!showRetry) return;
      const btn = document.getElementById(retryBtnId);
      if (btn) btn.addEventListener("click", onRetry);
    },
  };
}

window.GenerationCommon = {
  escapeHtml: genEscapeHtml,
  formatDate: genFormatDate,
  jobStatusBadge: genJobStatusBadge,
  docStatusBadge: genDocStatusBadge,
  pollJob: genPollJob,
  loadProjectOptions: genLoadProjectOptions,
  renderCapabilityBanner: genRenderCapabilityBanner,
  renderJobErrorCard: genRenderJobErrorCard,
};
