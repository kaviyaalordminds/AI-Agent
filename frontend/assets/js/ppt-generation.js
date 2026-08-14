let pptSlides = [];
let pptSlideSeq = 0;
let pptDocuments = [];

const SLIDE_LAYOUTS = [
  { key: "title_content", label: "Title + bullets" },
  { key: "title", label: "Title slide" },
  { key: "section_header", label: "Section header" },
  { key: "blank", label: "Blank" },
];

function newSlide() {
  pptSlideSeq += 1;
  return { id: `s${pptSlideSeq}`, title: "", layout: "title_content", subtitle: "", bullets: [""], notes: "" };
}

function renderSlideCard(slide, index) {
  const esc = window.GenerationCommon.escapeHtml;
  const showBullets = slide.layout === "title_content";
  const showSubtitle = slide.layout === "title";
  return `
    <div class="slide-card" data-slide-id="${slide.id}">
      <div class="slide-card-head">
        <span class="badge-pill badge-muted">Slide ${index + 1}</span>
        <select class="form-control-premium" style="width:auto;" data-field="layout">
          ${SLIDE_LAYOUTS.map((l) => `<option value="${l.key}" ${slide.layout === l.key ? "selected" : ""}>${l.label}</option>`).join("")}
        </select>
        <button type="button" class="slide-remove-btn" data-remove-slide title="Remove slide"><i class="bi bi-trash3"></i></button>
      </div>
      <input type="text" class="form-control-premium mb-2" data-field="title" placeholder="Slide title" value="${esc(slide.title)}">
      ${showSubtitle ? `<input type="text" class="form-control-premium mb-2" data-field="subtitle" placeholder="Subtitle" value="${esc(slide.subtitle)}">` : ""}
      ${showBullets ? `<textarea class="form-control-premium list-items-input mb-2" data-field="bullets" placeholder="One bullet per line">${esc(slide.bullets.join("\n"))}</textarea>` : ""}
      <input type="text" class="form-control-premium" data-field="notes" placeholder="Speaker notes (optional)" value="${esc(slide.notes)}">
    </div>
  `;
}

function renderSlides() {
  const container = document.getElementById("ppt-slides");
  container.innerHTML = pptSlides.map((s, i) => renderSlideCard(s, i)).join("");

  container.querySelectorAll("[data-slide-id]").forEach((card) => {
    const slide = pptSlides.find((s) => s.id === card.dataset.slideId);

    card.querySelector("[data-remove-slide]").addEventListener("click", () => {
      pptSlides = pptSlides.filter((s) => s.id !== slide.id);
      renderSlides();
    });

    card.querySelector('[data-field="layout"]').addEventListener("change", (e) => {
      slide.layout = e.target.value;
      renderSlides();
    });
    card.querySelector('[data-field="title"]').addEventListener("input", (e) => (slide.title = e.target.value));
    card.querySelector('[data-field="notes"]').addEventListener("input", (e) => (slide.notes = e.target.value));

    const subtitleField = card.querySelector('[data-field="subtitle"]');
    if (subtitleField) subtitleField.addEventListener("input", (e) => (slide.subtitle = e.target.value));

    const bulletsField = card.querySelector('[data-field="bullets"]');
    if (bulletsField) bulletsField.addEventListener("input", (e) => (slide.bullets = e.target.value.split("\n")));
  });
}

function setFieldError(field, message) {
  const el = document.querySelector(`[data-error-for="${field}"]`);
  if (!el) return;
  el.textContent = message || "";
  el.classList.toggle("visible", Boolean(message));
}

function slidesToPayload() {
  return pptSlides.map((s) => ({
    title: s.title,
    layout: s.layout,
    subtitle: s.layout === "title" ? s.subtitle : undefined,
    bullets: s.layout === "title_content" ? s.bullets.map((b) => b.trim()).filter(Boolean) : [],
    notes: s.notes || undefined,
  }));
}

function downloadDocUrl(id) {
  return `${window.AIAgentApi.apiBase()}/documents/${id}/download`;
}

function renderResult(doc) {
  const panel = document.getElementById("ppt-result-panel");
  panel.style.display = "";
  document.getElementById("ppt-result-title").textContent = doc.title;
  document.getElementById("ppt-result-status").innerHTML = window.GenerationCommon.docStatusBadge(doc.status);

  const body = document.getElementById("ppt-result-body");
  if (doc.status === "failed") {
    body.innerHTML = `<div class="alert-inline visible error">${window.GenerationCommon.escapeHtml(doc.error || "This presentation could not be generated.")}</div>`;
    return;
  }
  body.innerHTML = `
    <div class="d-flex align-items-center gap-2">
      <span style="font-size:0.78rem; color:var(--text-muted);">${doc.size_bytes ? `${(doc.size_bytes / 1024).toFixed(1)} KB` : ""}</span>
      <a class="btn-brand ms-auto" style="padding:0.4rem 0.9rem; font-size:0.82rem;" href="${downloadDocUrl(doc.id)}" target="_blank" rel="noopener"><i class="bi bi-download"></i> Download</a>
    </div>
  `;
}

function renderList() {
  const listEl = document.getElementById("ppt-list");
  const emptyEl = document.getElementById("ppt-list-empty");
  const docs = pptDocuments.filter((d) => d.format === "pptx");
  if (!docs.length) {
    listEl.innerHTML = "";
    emptyEl.classList.remove("d-none");
    return;
  }
  emptyEl.classList.add("d-none");
  listEl.innerHTML = docs
    .map(
      (d) => `
    <div class="gen-list-row" data-id="${d.id}">
      <div class="min-width-0 flex-grow-1" style="cursor:pointer;" data-view="${d.id}">
        <div class="gen-title text-truncate">${window.GenerationCommon.escapeHtml(d.title)}</div>
        <div class="gen-meta">${window.GenerationCommon.docStatusBadge(d.status)} · ${window.GenerationCommon.formatDate(d.created_at)}${d.project_name ? ` · ${window.GenerationCommon.escapeHtml(d.project_name)}` : ""}</div>
      </div>
      <div class="gen-actions">
        ${d.status === "completed" ? `<a class="btn-ghost" style="padding:0.35rem 0.6rem;" href="${downloadDocUrl(d.id)}" target="_blank" rel="noopener" title="Download"><i class="bi bi-download"></i></a>` : ""}
      </div>
    </div>`
    )
    .join("");

  listEl.querySelectorAll("[data-view]").forEach((el) => {
    el.addEventListener("click", () => {
      const doc = docs.find((d) => d.id === el.dataset.view);
      if (doc) renderResult(doc);
    });
  });
}

async function loadDocuments() {
  try {
    pptDocuments = await window.AIAgentApi.get("/documents");
    renderList();
  } catch {
    window.AIAgentToast.show("Could not load your presentations.", "error");
  }
}

async function generatePpt() {
  const title = document.getElementById("ppt-title").value.trim();
  const subtitle = document.getElementById("ppt-subtitle").value.trim();
  const projectId = document.getElementById("ppt-project").value;
  setFieldError("title", "");
  setFieldError("slides", "");

  if (!title) {
    setFieldError("title", "Give the presentation a title.");
    return;
  }
  if (!pptSlides.length) {
    setFieldError("slides", "Add at least one slide.");
    return;
  }

  const btn = document.getElementById("ppt-generate-btn");
  const originalLabel = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Generating…`;

  try {
    const doc = await window.AIAgentApi.post("/generation/document/ppt", {
      title,
      subtitle: subtitle || undefined,
      slides: slidesToPayload(),
      project_id: projectId || undefined,
    });
    renderResult(doc);
    await loadDocuments();
    window.AIAgentToast.show(doc.status === "completed" ? "Presentation generated." : "Generation failed.", doc.status === "completed" ? "success" : "error");
  } catch (err) {
    if (err.status === 422) {
      const fieldError = (err.fieldErrors || [])[0];
      window.AIAgentToast.show(fieldError ? fieldError.message : err.message, "error");
    } else {
      window.AIAgentToast.show(err.message, "error");
    }
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalLabel;
  }
}

async function init() {
  const user = await window.AppShell.initAppShell("presentations");
  if (!user) return;

  pptSlides = [newSlide()];
  renderSlides();

  document.getElementById("ppt-add-slide").addEventListener("click", () => {
    pptSlides.push(newSlide());
    renderSlides();
  });
  document.getElementById("ppt-generate-btn").addEventListener("click", generatePpt);

  await Promise.all([window.GenerationCommon.loadProjectOptions("ppt-project"), loadDocuments()]);
}

init();
