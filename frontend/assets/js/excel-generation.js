let excelSheets = [];
let excelSheetSeq = 0;
let excelDocuments = [];

const CHART_TYPES = [
  { key: "bar", label: "Bar" },
  { key: "line", label: "Line" },
  { key: "pie", label: "Pie" },
];

function newSheet() {
  excelSheetSeq += 1;
  return {
    id: `sh${excelSheetSeq}`,
    name: excelSheetSeq === 1 ? "Sheet1" : `Sheet${excelSheetSeq}`,
    headers: ["Column A", "Column B"],
    rows: [["", ""]],
    freezeHeader: true,
    charts: [],
  };
}

function renderChartRow(sheet, chart) {
  const esc = window.GenerationCommon.escapeHtml;
  return `
    <div class="chart-config-row" data-chart-id="${chart.id}">
      <select class="form-control-premium" data-chart-field="type">
        ${CHART_TYPES.map((t) => `<option value="${t.key}" ${chart.type === t.key ? "selected" : ""}>${t.label}</option>`).join("")}
      </select>
      <select class="form-control-premium" data-chart-field="category">
        ${sheet.headers.map((h) => `<option value="${esc(h)}" ${chart.category === h ? "selected" : ""}>${esc(h)}</option>`).join("")}
      </select>
      <input type="text" class="form-control-premium" data-chart-field="title" placeholder="Chart title" value="${esc(chart.title)}">
      <button type="button" class="row-remove-btn" data-remove-chart title="Remove chart"><i class="bi bi-x-lg"></i></button>
    </div>
    <div class="mb-2" style="font-size:0.78rem;">
      ${sheet.headers
        .map(
          (h) => `<label class="me-3"><input type="checkbox" data-chart-value-col="${esc(h)}" ${chart.valueColumns.includes(h) ? "checked" : ""}> ${esc(h)}</label>`
        )
        .join("")}
    </div>
  `;
}

function renderSheetCard(sheet, index) {
  const esc = window.GenerationCommon.escapeHtml;
  return `
    <div class="sheet-card" data-sheet-id="${sheet.id}">
      <div class="sheet-card-head">
        <input type="text" class="form-control-premium" style="max-width:200px;" data-field="name" value="${esc(sheet.name)}" placeholder="Sheet name" maxlength="31">
        <button type="button" class="sheet-remove-btn" data-remove-sheet title="Remove sheet"><i class="bi bi-trash3"></i></button>
      </div>

      <div class="grid-editor-wrap">
        <table class="grid-editor">
          <thead><tr>
            ${sheet.headers.map((h, c) => `<th><input type="text" class="form-control-premium" data-header-col="${c}" value="${esc(h)}" placeholder="Header"></th>`).join("")}
            <th></th>
          </tr></thead>
          <tbody>
            ${sheet.rows
              .map(
                (row, r) => `<tr>${row.map((cell, c) => `<td><input type="text" class="form-control-premium" data-row="${r}" data-col="${c}" value="${esc(cell)}"></td>`).join("")}<td><button type="button" class="row-remove-btn" data-remove-row="${r}" title="Remove row"><i class="bi bi-x-lg"></i></button></td></tr>`
              )
              .join("")}
          </tbody>
        </table>
      </div>
      <div class="grid-row-controls">
        <button type="button" class="btn-ghost" data-add-row style="padding:0.3rem 0.7rem; font-size:0.78rem;"><i class="bi bi-plus-lg"></i> Row</button>
        <button type="button" class="btn-ghost" data-add-col style="padding:0.3rem 0.7rem; font-size:0.78rem;"><i class="bi bi-plus-lg"></i> Column</button>
        <label style="font-size:0.78rem; margin-left:auto;"><input type="checkbox" data-field="freezeHeader" ${sheet.freezeHeader ? "checked" : ""}> Freeze header row</label>
      </div>

      <div class="mt-3">
        <label class="field-label">Charts <span style="font-weight:400; color:var(--text-muted);">(optional)</span></label>
        <div data-charts-container>${sheet.charts.map((c) => renderChartRow(sheet, c)).join("")}</div>
        <button type="button" class="btn-ghost" data-add-chart style="padding:0.3rem 0.7rem; font-size:0.78rem;"><i class="bi bi-plus-lg"></i> Add chart</button>
      </div>
    </div>
  `;
}

function wireChart(sheet, card) {
  card.querySelectorAll("[data-chart-id]").forEach((chartRow) => {
    const chart = sheet.charts.find((c) => c.id === chartRow.dataset.chartId);
    chartRow.querySelector('[data-chart-field="type"]').addEventListener("change", (e) => (chart.type = e.target.value));
    chartRow.querySelector('[data-chart-field="category"]').addEventListener("change", (e) => (chart.category = e.target.value));
    chartRow.querySelector('[data-chart-field="title"]').addEventListener("input", (e) => (chart.title = e.target.value));
    chartRow.querySelector("[data-remove-chart]").addEventListener("click", () => {
      sheet.charts = sheet.charts.filter((c) => c.id !== chart.id);
      renderSheets();
    });
  });
  card.querySelectorAll("[data-chart-value-col]").forEach((checkbox) => {
    checkbox.addEventListener("change", (e) => {
      const chartRow = e.target.closest("[data-chart-id]");
      const chart = sheet.charts.find((c) => c.id === chartRow.dataset.chartId);
      const col = e.target.dataset.chartValueCol;
      if (e.target.checked) {
        if (!chart.valueColumns.includes(col)) chart.valueColumns.push(col);
      } else {
        chart.valueColumns = chart.valueColumns.filter((v) => v !== col);
      }
    });
  });
}

function renderSheets() {
  const container = document.getElementById("excel-sheets");
  container.innerHTML = excelSheets.map(renderSheetCard).join("");

  container.querySelectorAll("[data-sheet-id]").forEach((card) => {
    const sheet = excelSheets.find((s) => s.id === card.dataset.sheetId);

    card.querySelector("[data-remove-sheet]").addEventListener("click", () => {
      excelSheets = excelSheets.filter((s) => s.id !== sheet.id);
      renderSheets();
    });
    card.querySelector('[data-field="name"]').addEventListener("input", (e) => (sheet.name = e.target.value));
    card.querySelector('[data-field="freezeHeader"]').addEventListener("change", (e) => (sheet.freezeHeader = e.target.checked));

    card.querySelectorAll("[data-header-col]").forEach((input) => {
      input.addEventListener("input", (e) => {
        sheet.headers[Number(e.target.dataset.headerCol)] = e.target.value;
      });
    });
    card.querySelectorAll("[data-row][data-col]").forEach((input) => {
      input.addEventListener("input", (e) => {
        sheet.rows[Number(e.target.dataset.row)][Number(e.target.dataset.col)] = e.target.value;
      });
    });
    card.querySelectorAll("[data-remove-row]").forEach((btn) => {
      btn.addEventListener("click", () => {
        if (sheet.rows.length <= 1) return;
        sheet.rows.splice(Number(btn.dataset.removeRow), 1);
        renderSheets();
      });
    });
    card.querySelector("[data-add-row]").addEventListener("click", () => {
      sheet.rows.push(sheet.headers.map(() => ""));
      renderSheets();
    });
    card.querySelector("[data-add-col]").addEventListener("click", () => {
      sheet.headers.push(`Column ${String.fromCharCode(65 + sheet.headers.length)}`);
      sheet.rows.forEach((row) => row.push(""));
      renderSheets();
    });
    card.querySelector("[data-add-chart]").addEventListener("click", () => {
      sheet.charts.push({
        id: `c${Date.now()}${Math.random().toString(36).slice(2, 6)}`,
        type: "bar",
        title: "",
        category: sheet.headers[0] || "",
        valueColumns: [],
      });
      renderSheets();
    });

    wireChart(sheet, card);
  });
}

function setFieldError(field, message) {
  const el = document.querySelector(`[data-error-for="${field}"]`);
  if (!el) return;
  el.textContent = message || "";
  el.classList.toggle("visible", Boolean(message));
}

function sheetsToPayload() {
  return excelSheets.map((s) => ({
    name: s.name || "Sheet1",
    headers: s.headers,
    rows: s.rows.map((row) => row.map((cell) => (cell === "" ? null : isNaN(Number(cell)) ? cell : Number(cell)))),
    freeze_header: s.freezeHeader,
    charts: s.charts
      .filter((c) => c.category && c.valueColumns.length)
      .map((c) => ({
        type: c.type,
        title: c.title || undefined,
        category_column: c.category,
        value_columns: c.valueColumns,
      })),
  }));
}

function downloadDocUrl(id) {
  return `${window.AIAgentApi.apiBase()}/documents/${id}/download`;
}

function renderResult(doc) {
  const panel = document.getElementById("excel-result-panel");
  panel.style.display = "";
  document.getElementById("excel-result-title").textContent = doc.title;
  document.getElementById("excel-result-status").innerHTML = window.GenerationCommon.docStatusBadge(doc.status);

  const body = document.getElementById("excel-result-body");
  if (doc.status === "failed") {
    body.innerHTML = `<div class="alert-inline visible error">${window.GenerationCommon.escapeHtml(doc.error || "This spreadsheet could not be generated.")}</div>`;
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
  const listEl = document.getElementById("excel-list");
  const emptyEl = document.getElementById("excel-list-empty");
  const docs = excelDocuments.filter((d) => d.format === "xlsx");
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
    excelDocuments = await window.AIAgentApi.get("/documents");
    renderList();
  } catch {
    window.AIAgentToast.show("Could not load your spreadsheets.", "error");
  }
}

async function generateExcel() {
  const title = document.getElementById("excel-title").value.trim();
  const projectId = document.getElementById("excel-project").value;
  setFieldError("title", "");
  setFieldError("sheets", "");

  if (!title) {
    setFieldError("title", "Give the workbook a title.");
    return;
  }
  if (!excelSheets.length) {
    setFieldError("sheets", "Add at least one sheet.");
    return;
  }

  const btn = document.getElementById("excel-generate-btn");
  const originalLabel = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Generating…`;

  try {
    const doc = await window.AIAgentApi.post("/generation/document/excel", {
      title,
      sheets: sheetsToPayload(),
      project_id: projectId || undefined,
    });
    renderResult(doc);
    await loadDocuments();
    window.AIAgentToast.show(doc.status === "completed" ? "Spreadsheet generated." : "Generation failed.", doc.status === "completed" ? "success" : "error");
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
  const user = await window.AppShell.initAppShell("excel");
  if (!user) return;

  excelSheets = [newSheet()];
  renderSheets();

  document.getElementById("excel-add-sheet").addEventListener("click", () => {
    excelSheets.push(newSheet());
    renderSheets();
  });
  document.getElementById("excel-generate-btn").addEventListener("click", generateExcel);

  await Promise.all([window.GenerationCommon.loadProjectOptions("excel-project"), loadDocuments()]);
}

init();
