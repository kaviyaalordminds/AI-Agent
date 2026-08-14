function ensureToastStack() {
  let stack = document.getElementById("toast-stack");
  if (!stack) {
    stack = document.createElement("div");
    stack.id = "toast-stack";
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
