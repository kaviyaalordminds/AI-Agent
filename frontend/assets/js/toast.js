function ensureToastStack() {
  let stack = document.getElementById("toast-stack");
  if (!stack) {
    stack = document.createElement("div");
    stack.id = "toast-stack";
    // Every toast (generation results, save/delete confirmations, errors)
    // was previously invisible to screen readers — role="status" +
    // aria-live="polite" makes new toasts announced automatically without
    // interrupting whatever the user is currently doing.
    stack.setAttribute("role", "status");
    stack.setAttribute("aria-live", "polite");
    document.body.appendChild(stack);
  }
  return stack;
}

const TOAST_ICONS = { success: "bi-check-circle-fill", error: "bi-x-circle-fill", info: "bi-info-circle-fill" };

function showToast(message, type = "info", duration = 5000) {
  const stack = ensureToastStack();
  const el = document.createElement("div");
  el.className = `toast-item ${type}`;
  el.innerHTML = `<i class="bi ${TOAST_ICONS[type] || TOAST_ICONS.info}"></i><span>${message}</span>`;
  stack.appendChild(el);
  setTimeout(() => {
    el.style.opacity = "0";
    el.style.transition = "opacity 200ms ease";
    setTimeout(() => el.remove(), 200);
  }, duration);
}

window.AIAgentToast = { show: showToast };
