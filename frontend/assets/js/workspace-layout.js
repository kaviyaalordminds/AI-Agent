/* Reusable split-screen + full-screen workspace controller. Any tool page
 * can call `WorkspaceLayout.initSplitView(...)` on a `.split-view` element
 * to get a draggable, preset-snappable, persisted two-pane layout, and
 * `WorkspaceLayout.initFullscreenToggle(...)` to get a full-screen toggle
 * that hides the app chrome. Both are storage-key-scoped so multiple tools
 * can each remember their own layout independently. */

const MIN_RATIO = 20;
const MAX_RATIO = 80;
const PRESETS = [
  { key: "40-60", ratio: 40, label: "40 / 60" },
  { key: "50-50", ratio: 50, label: "50 / 50" },
  { key: "60-40", ratio: 60, label: "60 / 40" },
];

function clamp(n, min, max) {
  return Math.min(max, Math.max(min, n));
}

function initSplitView(container, { storageKey, stacked = false, presetsEl } = {}) {
  const stored = storageKey ? Number(localStorage.getItem(storageKey)) : NaN;
  let ratio = clamp(Number.isFinite(stored) && stored ? stored : 50, MIN_RATIO, MAX_RATIO);

  if (stacked) container.classList.add("split-stacked");
  container.style.setProperty("--split-ratio", ratio);

  function applyRatio(newRatio) {
    ratio = clamp(newRatio, MIN_RATIO, MAX_RATIO);
    container.style.setProperty("--split-ratio", ratio);
    if (storageKey) localStorage.setItem(storageKey, String(ratio));
    if (presetsEl) syncPresetButtons();
  }

  function syncPresetButtons() {
    presetsEl.querySelectorAll("button[data-ratio]").forEach((btn) => {
      btn.classList.toggle("active", Number(btn.dataset.ratio) === ratio);
    });
  }

  const divider = container.querySelector(".split-divider");
  if (divider) {
    let dragging = false;

    const onPointerMove = (e) => {
      if (!dragging) return;
      const rect = container.getBoundingClientRect();
      const pos = stacked
        ? ((e.clientY - rect.top) / rect.height) * 100
        : ((e.clientX - rect.left) / rect.width) * 100;
      applyRatio(pos);
    };
    const stopDragging = () => {
      dragging = false;
      divider.classList.remove("dragging");
      document.removeEventListener("pointermove", onPointerMove);
      document.removeEventListener("pointerup", stopDragging);
    };

    divider.addEventListener("pointerdown", (e) => {
      dragging = true;
      divider.classList.add("dragging");
      e.preventDefault();
      document.addEventListener("pointermove", onPointerMove);
      document.addEventListener("pointerup", stopDragging);
    });
  }

  if (presetsEl) {
    presetsEl.innerHTML = PRESETS.map(
      (p) => `<button type="button" data-ratio="${p.ratio}">${p.label}</button>`
    ).join("");
    presetsEl.querySelectorAll("button[data-ratio]").forEach((btn) => {
      btn.addEventListener("click", () => applyRatio(Number(btn.dataset.ratio)));
    });
    syncPresetButtons();
  }

  return { applyRatio, getRatio: () => ratio };
}

function initFullscreenToggle(button, { shellSelector = ".app-shell" } = {}) {
  const shell = document.querySelector(shellSelector);
  button.addEventListener("click", () => {
    const active = shell.classList.toggle("workspace-fullscreen-active");
    button.innerHTML = active
      ? '<i class="bi bi-fullscreen-exit"></i> Exit full screen'
      : '<i class="bi bi-arrows-fullscreen"></i> Full screen';
  });
}

window.WorkspaceLayout = { initSplitView, initFullscreenToggle };
