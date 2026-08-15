/* Shared rendering for history entries, used by both the standalone
 * History page and a project workspace's History tab. */

const HISTORY_TYPE_ICONS = {
  chat: "bi-chat-dots",
  image: "bi-image",
  video: "bi-camera-reels",
  audio: "bi-mic",
  document: "bi-file-earmark-text",
  website: "bi-globe",
  poster: "bi-file-earmark-image",
  logo: "bi-vector-pen",
  graphic_design: "bi-palette",
  deployment: "bi-cloud-arrow-up",
  knowledge_update: "bi-arrow-repeat",
};

const HISTORY_STATUS_BADGES = {
  queued: "badge-muted",
  processing: "badge-info",
  completed: "badge-success",
  failed: "badge-danger",
};

function historyFormatDate(iso) {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function historyTypeLabel(type) {
  return type
    .split("_")
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(" ");
}

function historyEscapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function renderHistoryRows(items, { showProject = true } = {}) {
  const header = `
    <div class="history-table-row header">
      <span>Task</span>
      <span>Type</span>
      ${showProject ? "<span>Project</span>" : "<span>Status</span>"}
      <span>Date</span>
      <span></span>
    </div>`;

  const rows = items
    .map(
      (item) => `
    <div class="history-table-row" data-entry-id="${item.id}">
      <span class="text-truncate">${historyEscapeHtml(item.title)}</span>
      <span><i class="bi ${HISTORY_TYPE_ICONS[item.type] || "bi-file"}"></i> ${historyTypeLabel(item.type)}</span>
      ${
        showProject
          ? `<span class="text-truncate">${item.project_name ? historyEscapeHtml(item.project_name) : '<span style="opacity:0.5;">—</span>'}</span>`
          : `<span class="badge-pill ${HISTORY_STATUS_BADGES[item.status]}">${historyTypeLabel(item.status)}</span>`
      }
      <span style="color:var(--text-muted); font-size:0.8rem;">${historyFormatDate(item.created_at)}</span>
      <span>
        <button type="button" class="btn-ghost history-delete-btn" data-entry-id="${item.id}" aria-label="Delete" title="Delete" style="padding:0.3rem 0.6rem; font-size:0.76rem;">
          <i class="bi bi-trash3"></i>
        </button>
      </span>
    </div>`
    )
    .join("");

  return header + rows;
}

function wireHistoryDeleteButtons(container, onDeleted) {
  container.querySelectorAll(".history-delete-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const confirmed = await window.AIAgentModals.confirmAction({
        title: "Delete this history entry?",
        message: "This removes it from your history. This cannot be undone.",
        confirmLabel: "Delete",
        danger: true,
      });
      if (!confirmed) return;
      try {
        await window.AIAgentApi.del(`/history/${btn.dataset.entryId}`);
        window.AIAgentToast.show("History entry deleted.", "success");
        onDeleted();
      } catch (err) {
        window.AIAgentToast.show(err.message, "error");
      }
    });
  });
}

window.HistoryCommon = { renderHistoryRows, wireHistoryDeleteButtons };
