/* Generic confirmation modal, reusable anywhere a destructive or
 * significant action needs a premium (non-native-browser-dialog)
 * confirmation. Injects one Bootstrap modal instance into the page. */
function ensureConfirmModal() {
  let el = document.getElementById("confirm-modal");
  if (el) return el;
  el = document.createElement("div");
  el.id = "confirm-modal";
  el.className = "modal fade";
  el.tabIndex = -1;
  el.innerHTML = `
    <div class="modal-dialog modal-dialog-centered">
      <div class="modal-content surface">
        <div class="modal-body p-4">
          <h5 id="confirm-modal-title" class="mb-2"></h5>
          <p id="confirm-modal-message" class="mb-4" style="color:var(--text-muted); font-size:0.9rem;"></p>
          <div class="d-flex justify-content-end gap-2">
            <button type="button" class="btn-ghost" data-bs-dismiss="modal">Cancel</button>
            <button type="button" id="confirm-modal-confirm-btn" class="btn-brand"></button>
          </div>
        </div>
      </div>
    </div>`;
  document.body.appendChild(el);
  return el;
}

function confirmAction({ title, message, confirmLabel = "Confirm", danger = false }) {
  const el = ensureConfirmModal();
  document.getElementById("confirm-modal-title").textContent = title;
  document.getElementById("confirm-modal-message").textContent = message;
  const confirmBtn = document.getElementById("confirm-modal-confirm-btn");
  confirmBtn.textContent = confirmLabel;
  confirmBtn.style.background = danger ? "var(--danger)" : "";
  confirmBtn.style.boxShadow = danger ? "none" : "";

  const modal = new bootstrap.Modal(el);

  return new Promise((resolve) => {
    const onConfirm = () => {
      cleanup();
      modal.hide();
      resolve(true);
    };
    const onHidden = () => {
      cleanup();
      resolve(false);
    };
    function cleanup() {
      confirmBtn.removeEventListener("click", onConfirm);
      el.removeEventListener("hidden.bs.modal", onHidden);
    }
    confirmBtn.addEventListener("click", onConfirm);
    el.addEventListener("hidden.bs.modal", onHidden);
    modal.show();
  });
}

window.AIAgentModals = { confirmAction };
