let currentPath = null;
let vaultFolders = [];
let newNoteModal, moveNoteModal;
let isDirty = false;

function obsEscapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function obsFormatDate(iso) {
  return new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function encodePath(path) {
  return path.split("/").map(encodeURIComponent).join("/");
}

/* Minimal, safe markdown-ish renderer: escapes everything first, then
 * applies a handful of Obsidian-flavored replacements. Not a full
 * CommonMark implementation — just enough to make notes readable without
 * pulling in an external library. */
function renderMarkdownPreview(content) {
  let html = obsEscapeHtml(content);
  html = html.replace(/^### (.*)$/gm, "<h3>$1</h3>");
  html = html.replace(/^## (.*)$/gm, "<h2>$1</h2>");
  html = html.replace(/^# (.*)$/gm, "<h1>$1</h1>");
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, "<em>$1</em>");
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
  html = html.replace(/\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]/g, '<a class="wiki-link" href="#">$1</a>');
  html = html.replace(/(?<!\S)#([A-Za-z0-9_/-]+)/g, '<span class="tag-chip">#$1</span>');
  html = html
    .split(/\n{2,}/)
    .map((block) => (block.startsWith("<h1") || block.startsWith("<h2") || block.startsWith("<h3") ? block : `<p>${block.replace(/\n/g, "<br>")}</p>`))
    .join("\n");
  return html;
}

async function loadStatus() {
  try {
    const s = await window.AIAgentApi.get("/obsidian/status");
    vaultFolders = s.folders;
    const badge = document.getElementById("vault-status-badge");
    badge.className = "badge-pill badge-success";
    badge.innerHTML = `<span class="dot dot-success"></span> Connected — ${s.note_count} notes`;

    const folderFilter = document.getElementById("vault-folder-filter");
    const newNoteFolder = document.getElementById("new-note-folder");
    folderFilter.innerHTML = '<option value="">All folders</option>' + vaultFolders.map((f) => `<option value="${f}">${f}</option>`).join("");
    newNoteFolder.innerHTML = vaultFolders.map((f) => `<option value="${f}">${f}</option>`).join("");
  } catch (err) {
    const badge = document.getElementById("vault-status-badge");
    badge.className = "badge-pill badge-danger";
    badge.innerHTML = `<span class="dot dot-danger"></span> Error`;
    window.AIAgentToast.show(err.message, "error");
  }
}

function noteItemHtml(note) {
  return `
    <div class="note-item ${note.path === currentPath ? "active" : ""}" data-path="${obsEscapeHtml(note.path)}">
      <div class="note-item-title">${obsEscapeHtml(note.title)}</div>
      <div class="note-item-folder">${obsEscapeHtml(note.folder || "/")} · ${obsFormatDate(note.updated_at)}</div>
      <div class="note-item-excerpt">${obsEscapeHtml(note.excerpt) || '<span style="opacity:0.5;">Empty note</span>'}</div>
      ${note.tags.length ? `<div class="note-item-tags">${note.tags.map((t) => `<span class="tag-chip">#${obsEscapeHtml(t)}</span>`).join("")}</div>` : ""}
    </div>`;
}

async function loadNotes() {
  const container = document.getElementById("vault-notes");
  const search = document.getElementById("vault-search").value.trim();
  const folder = document.getElementById("vault-folder-filter").value;
  const params = new URLSearchParams();
  if (search) params.set("search", search);
  else if (folder) params.set("folder", folder);

  try {
    const notes = await window.AIAgentApi.get(`/obsidian/notes?${params.toString()}`);
    if (!notes.length) {
      container.innerHTML = `<div class="empty-state" style="padding:2rem 1rem;"><p style="font-size:0.82rem;">${search ? "No matching notes." : "No notes yet."}</p></div>`;
      return;
    }
    container.innerHTML = notes.map(noteItemHtml).join("");
    container.querySelectorAll(".note-item").forEach((el) => {
      el.addEventListener("click", () => selectNote(el.dataset.path));
    });
  } catch (err) {
    container.innerHTML = `<div class="empty-state" style="padding:2rem 1rem;"><p>${err.message}</p></div>`;
  }
}

function setEditorView(view) {
  const textarea = document.getElementById("note-content");
  const preview = document.getElementById("note-preview");
  document.querySelectorAll("#editor-tabs button").forEach((b) => b.classList.toggle("active", b.dataset.view === view));
  if (view === "preview") {
    preview.innerHTML = renderMarkdownPreview(textarea.value);
    textarea.classList.add("d-none");
    preview.classList.remove("d-none");
  } else {
    textarea.classList.remove("d-none");
    preview.classList.add("d-none");
  }
}

async function selectNote(path) {
  if (isDirty && path !== currentPath) {
    const proceed = await window.AIAgentModals.confirmAction({
      title: "Discard unsaved changes?",
      message: "You have unsaved edits to the current note. Switching notes will discard them.",
      confirmLabel: "Discard",
      danger: true,
    });
    if (!proceed) return;
  }
  currentPath = path;
  document.getElementById("detail-empty").classList.add("d-none");
  document.getElementById("detail-active").classList.remove("d-none");
  document.querySelectorAll(".note-item").forEach((el) => el.classList.toggle("active", el.dataset.path === path));

  try {
    const note = await window.AIAgentApi.get(`/obsidian/notes/${encodePath(path)}`);
    document.getElementById("detail-path").textContent = note.path;
    document.getElementById("note-content").value = note.content;
    document.getElementById("detail-tags").innerHTML = note.tags.map((t) => `<span class="tag-chip">#${obsEscapeHtml(t)}</span>`).join("") || '<span style="font-size:0.78rem; color:var(--text-muted);">No tags</span>';
    isDirty = false;
    setEditorView("edit");
  } catch (err) {
    window.AIAgentToast.show(err.message, "error");
  }

  document.getElementById("vault-list-pane").classList.remove("mobile-open");
}

async function saveNote() {
  if (!currentPath) return;
  const content = document.getElementById("note-content").value;
  try {
    const note = await putNote(currentPath, content);
    document.getElementById("detail-tags").innerHTML = note.tags.map((t) => `<span class="tag-chip">#${obsEscapeHtml(t)}</span>`).join("") || '<span style="font-size:0.78rem; color:var(--text-muted);">No tags</span>';
    window.AIAgentToast.show("Note saved.", "success");
    isDirty = false;
    loadNotes();
    loadStatus();
  } catch (err) {
    window.AIAgentToast.show(err.message, "error");
  }
}

async function putNote(path, content) {
  const resp = await fetch(`${window.AIAgentApi.apiBase()}/obsidian/notes/${encodePath(path)}`, {
    method: "PUT",
    credentials: "include",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": window.AIAgentApi.getCsrfToken() },
    body: JSON.stringify({ content }),
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${resp.status}).`);
  }
  return resp.json();
}

async function deleteCurrentNote() {
  if (!currentPath) return;
  const confirmed = await window.AIAgentModals.confirmAction({
    title: "Delete this note?",
    message: `"${currentPath}" will be permanently deleted.`,
    confirmLabel: "Delete",
    danger: true,
  });
  if (!confirmed) return;
  try {
    await window.AIAgentApi.del(`/obsidian/notes/${encodePath(currentPath)}`);
    window.AIAgentToast.show("Note deleted.", "success");
    currentPath = null;
    document.getElementById("detail-active").classList.add("d-none");
    document.getElementById("detail-empty").classList.remove("d-none");
    loadNotes();
    loadStatus();
  } catch (err) {
    window.AIAgentToast.show(err.message, "error");
  }
}

function initNewNoteModal() {
  newNoteModal = new bootstrap.Modal(document.getElementById("new-note-modal"));
  document.getElementById("new-note-btn").addEventListener("click", () => {
    document.getElementById("new-note-form").reset();
    hideAlert(document.getElementById("new-note-alert"));
    newNoteModal.show();
  });

  document.getElementById("new-note-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.target;
    clearFieldErrors(form);
    const alertEl = document.getElementById("new-note-alert");
    hideAlert(alertEl);

    const folder = document.getElementById("new-note-folder").value;
    const filename = document.getElementById("new-note-filename").value.trim();
    if (!filename) {
      setFieldError(form, "filename", "File name is required.");
      return;
    }
    const path = `${folder}/${filename}.md`;

    const btn = document.getElementById("new-note-submit");
    setLoading(btn, true, "Creating…");
    try {
      await window.AIAgentApi.post("/obsidian/notes", { path, content: `# ${filename}\n\n` });
      newNoteModal.hide();
      window.AIAgentToast.show("Note created.", "success");
      await loadNotes();
      await loadStatus();
      selectNote(path);
    } catch (err) {
      showAlert(alertEl, err.message, "error");
    } finally {
      setLoading(btn, false);
    }
  });
}

function initMoveNoteModal() {
  moveNoteModal = new bootstrap.Modal(document.getElementById("move-note-modal"));
  document.getElementById("move-note-btn").addEventListener("click", () => {
    if (!currentPath) return;
    document.getElementById("move-note-path").value = currentPath;
    hideAlert(document.getElementById("move-note-alert"));
    moveNoteModal.show();
  });

  document.getElementById("move-note-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.target;
    clearFieldErrors(form);
    const alertEl = document.getElementById("move-note-alert");
    hideAlert(alertEl);
    const newPath = document.getElementById("move-note-path").value.trim();

    try {
      await window.AIAgentApi.post(`/obsidian/notes/${encodePath(currentPath)}/move`, { new_path: newPath });
      moveNoteModal.hide();
      window.AIAgentToast.show("Note moved.", "success");
      await loadNotes();
      selectNote(newPath);
    } catch (err) {
      if (!applyFieldErrorsFromApi(form, err)) showAlert(alertEl, err.message, "error");
    }
  });
}

async function init() {
  const user = await window.AppShell.initAppShell("obsidian");
  if (!user) return;

  initNewNoteModal();
  initMoveNoteModal();

  document.getElementById("save-note-btn").addEventListener("click", saveNote);
  document.getElementById("delete-note-btn").addEventListener("click", deleteCurrentNote);
  document.getElementById("note-content").addEventListener("input", () => {
    isDirty = true;
  });
  window.addEventListener("beforeunload", (e) => {
    if (!isDirty) return;
    e.preventDefault();
    e.returnValue = "";
  });
  document.querySelectorAll("#editor-tabs button").forEach((btn) => {
    btn.addEventListener("click", () => setEditorView(btn.dataset.view));
  });

  document.getElementById("mobile-list-toggle").addEventListener("click", () => {
    document.getElementById("vault-list-pane").classList.toggle("mobile-open");
  });

  let searchDebounce;
  document.getElementById("vault-search").addEventListener("input", () => {
    clearTimeout(searchDebounce);
    searchDebounce = setTimeout(loadNotes, 300);
  });
  document.getElementById("vault-folder-filter").addEventListener("change", loadNotes);

  await loadStatus();
  await loadNotes();
}

init();
