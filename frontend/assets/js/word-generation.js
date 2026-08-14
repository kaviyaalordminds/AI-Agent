let wordBlocks = [];
let wordBlockSeq = 0;
let wordDocuments = [];

function newBlock(type) {
  wordBlockSeq += 1;
  const base = { id: `b${wordBlockSeq}`, type };
  if (type === "heading") return { ...base, text: "", level: 1 };
  if (type === "paragraph") return { ...base, text: "", bold: false, italic: false };
  if (type === "bullet_list" || type === "numbered_list") return { ...base, items: [""] };
  if (type === "table") return { ...base, rows: [["", ""], ["", ""]], headerRow: true };
  return base;
}

const BLOCK_LABELS = {
  heading: "Heading",
  paragraph: "Paragraph",
  bullet_list: "Bullet list",
  numbered_list: "Numbered list",
  table: "Table",
};

function renderBlockCard(block) {
  const esc = window.GenerationCommon.escapeHtml;
  let inner = "";
  if (block.type === "heading") {
    inner = `
      <select class="form-control-premium mb-2" style="width:auto;" data-field="level">
        ${[1, 2, 3, 4].map((l) => `<option value="${l}" ${block.level === l ? "selected" : ""}>Heading ${l}</option>`).join("")}
      </select>
      <input type="text" class="form-control-premium" data-field="text" placeholder="Heading text" value="${esc(block.text)}">
    `;
  } else if (block.type === "paragraph") {
    inner = `
      <textarea class="form-control-premium" data-field="text" placeholder="Paragraph text">${esc(block.text)}</textarea>
      <div class="d-flex gap-3 mt-2" style="font-size:0.8rem;">
        <label><input type="checkbox" data-field="bold" ${block.bold ? "checked" : ""}> Bold</label>
        <label><input type="checkbox" data-field="italic" ${block.italic ? "checked" : ""}> Italic</label>
      </div>
    `;
  } else if (block.type === "bullet_list" || block.type === "numbered_list") {
    inner = `<textarea class="form-control-premium list-items-input" data-field="items" placeholder="One item per line">${esc(block.items.join("\n"))}</textarea>`;
  } else if (block.type === "table") {
    inner = `
      <div class="grid-editor-wrap">
        <table class="grid-editor"><tbody>
          ${block.rows
            .map(
              (row, r) => `<tr>${row.map((cell, c) => `<td><input type="text" class="form-control-premium" data-row="${r}" data-col="${c}" value="${esc(cell)}"></td>`).join("")}<td><button type="button" class="row-remove-btn" data-remove-row="${r}" title="Remove row"><i class="bi bi-x-lg"></i></button></td></tr>`
            )
            .join("")}
        </tbody></table>
      </div>
      <div class="grid-row-controls">
        <button type="button" class="btn-ghost" data-add-row style="padding:0.3rem 0.7rem; font-size:0.78rem;"><i class="bi bi-plus-lg"></i> Row</button>
        <button type="button" class="btn-ghost" data-add-col style="padding:0.3rem 0.7rem; font-size:0.78rem;"><i class="bi bi-plus-lg"></i> Column</button>
        <label style="font-size:0.78rem; margin-left:auto;"><input type="checkbox" data-field="headerRow" ${block.headerRow ? "checked" : ""}> First row is header</label>
      </div>
    `;
  }

  return `
    <div class="block-card" data-block-id="${block.id}">
      <div class="block-card-head">
        <span class="badge-pill badge-muted">${BLOCK_LABELS[block.type]}</span>
        <button type="button" class="block-remove-btn" data-remove-block title="Remove block"><i class="bi bi-trash3"></i></button>
      </div>
      ${inner}
    </div>
  `;
}

function renderBlocks() {
  const container = document.getElementById("word-blocks");
  container.innerHTML = wordBlocks.map(renderBlockCard).join("");

  container.querySelectorAll("[data-block-id]").forEach((card) => {
    const block = wordBlocks.find((b) => b.id === card.dataset.blockId);

    card.querySelector("[data-remove-block]").addEventListener("click", () => {
      wordBlocks = wordBlocks.filter((b) => b.id !== block.id);
      renderBlocks();
    });

    const textField = card.querySelector('[data-field="text"]');
    if (textField) textField.addEventListener("input", (e) => (block.text = e.target.value));

    const levelField = card.querySelector('[data-field="level"]');
    if (levelField) levelField.addEventListener("change", (e) => (block.level = Number(e.target.value)));

    const boldField = card.querySelector('[data-field="bold"]');
    if (boldField) boldField.addEventListener("change", (e) => (block.bold = e.target.checked));
    const italicField = card.querySelector('[data-field="italic"]');
    if (italicField) italicField.addEventListener("change", (e) => (block.italic = e.target.checked));

    const itemsField = card.querySelector('[data-field="items"]');
    if (itemsField) {
      itemsField.addEventListener("input", (e) => {
        block.items = e.target.value.split("\n");
      });
    }

    const headerRowField = card.querySelector('[data-field="headerRow"]');
    if (headerRowField) headerRowField.addEventListener("change", (e) => (block.headerRow = e.target.checked));

    card.querySelectorAll("[data-row][data-col]").forEach((input) => {
      input.addEventListener("input", (e) => {
        block.rows[Number(e.target.dataset.row)][Number(e.target.dataset.col)] = e.target.value;
      });
    });
    card.querySelectorAll("[data-remove-row]").forEach((btn) => {
      btn.addEventListener("click", () => {
        if (block.rows.length <= 1) return;
        block.rows.splice(Number(btn.dataset.removeRow), 1);
        renderBlocks();
      });
    });
    const addRowBtn = card.querySelector("[data-add-row]");
    if (addRowBtn) {
      addRowBtn.addEventListener("click", () => {
        block.rows.push(block.rows[0].map(() => ""));
        renderBlocks();
      });
    }
    const addColBtn = card.querySelector("[data-add-col]");
    if (addColBtn) {
      addColBtn.addEventListener("click", () => {
        block.rows.forEach((row) => row.push(""));
        renderBlocks();
      });
    }
  });
}

function setFieldError(field, message) {
  const el = document.querySelector(`[data-error-for="${field}"]`);
  if (!el) return;
  el.textContent = message || "";
  el.classList.toggle("visible", Boolean(message));
}

function blocksToPayload() {
  return wordBlocks.map((b) => {
    if (b.type === "heading") return { type: "heading", text: b.text, level: b.level };
    if (b.type === "paragraph") return { type: "paragraph", text: b.text, bold: b.bold, italic: b.italic };
    if (b.type === "bullet_list" || b.type === "numbered_list") {
      return { type: b.type, items: b.items.map((i) => i.trim()).filter(Boolean) };
    }
    if (b.type === "table") return { type: "table", rows: b.rows, header_row: b.headerRow };
    return b;
  });
}

function downloadDocUrl(id) {
  return `${window.AIAgentApi.apiBase()}/documents/${id}/download`;
}

function renderResult(doc) {
  const panel = document.getElementById("word-result-panel");
  panel.style.display = "";
  document.getElementById("word-result-title").textContent = doc.title;
  document.getElementById("word-result-status").innerHTML = window.GenerationCommon.docStatusBadge(doc.status);

  const body = document.getElementById("word-result-body");
  if (doc.status === "failed") {
    body.innerHTML = `<div class="alert-inline visible error">${window.GenerationCommon.escapeHtml(doc.error || "This document could not be generated.")}</div>`;
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
  const listEl = document.getElementById("word-list");
  const emptyEl = document.getElementById("word-list-empty");
  const docs = wordDocuments.filter((d) => d.format === "docx");
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
    wordDocuments = await window.AIAgentApi.get("/documents");
    renderList();
  } catch {
    window.AIAgentToast.show("Could not load your documents.", "error");
  }
}

async function generateWordDocument() {
  const title = document.getElementById("word-title").value.trim();
  const author = document.getElementById("word-author").value.trim();
  const projectId = document.getElementById("word-project").value;
  setFieldError("title", "");
  setFieldError("blocks", "");

  if (!title) {
    setFieldError("title", "Give the document a title.");
    return;
  }
  if (!wordBlocks.length) {
    setFieldError("blocks", "Add at least one block of content.");
    return;
  }

  const btn = document.getElementById("word-generate-btn");
  const originalLabel = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Generating…`;

  try {
    const doc = await window.AIAgentApi.post("/generation/document/word", {
      title,
      author: author || undefined,
      blocks: blocksToPayload(),
      project_id: projectId || undefined,
    });
    renderResult(doc);
    await loadDocuments();
    window.AIAgentToast.show(doc.status === "completed" ? "Word document generated." : "Generation failed.", doc.status === "completed" ? "success" : "error");
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
  const user = await window.AppShell.initAppShell("word");
  if (!user) return;

  wordBlocks = [newBlock("heading"), newBlock("paragraph")];
  renderBlocks();

  document.querySelectorAll("[data-add-block]").forEach((btn) => {
    btn.addEventListener("click", () => {
      wordBlocks.push(newBlock(btn.dataset.addBlock));
      renderBlocks();
    });
  });
  document.getElementById("word-generate-btn").addEventListener("click", generateWordDocument);

  await Promise.all([window.GenerationCommon.loadProjectOptions("word-project"), loadDocuments()]);
}

init();
