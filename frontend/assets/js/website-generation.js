const SITE_STYLES = [
  { key: "modern", label: "Modern" },
  { key: "minimal", label: "Minimal" },
  { key: "bold", label: "Bold" },
  { key: "corporate", label: "Corporate" },
  { key: "playful", label: "Playful" },
  { key: "3d", label: "3D Interactive" },
];

let selectedSiteStyle = "modern";
let pageNames = ["Home"];
let siteJobs = [];
let currentWebsite = null;

function previewUrl(websiteId, path) {
  return `${window.AIAgentApi.apiBase()}/websites/${websiteId}/preview/${path}`;
}

function downloadDeploymentUrl(websiteId) {
  return `${window.AIAgentApi.apiBase()}/websites/${websiteId}/deployment/download`;
}

function renderStylePicker() {
  const picker = document.getElementById("site-style-picker");
  picker.innerHTML = SITE_STYLES.map(
    (s) => `<button type="button" class="mode-pill ${s.key === selectedSiteStyle ? "active" : ""}" data-style="${s.key}">${s.label}</button>`
  ).join("");
  picker.querySelectorAll("[data-style]").forEach((btn) => {
    btn.addEventListener("click", () => {
      selectedSiteStyle = btn.dataset.style;
      renderStylePicker();
      document.getElementById("site-3d-note").classList.toggle("d-none", selectedSiteStyle !== "3d");
    });
  });
}

function renderPagesList() {
  const el = document.getElementById("site-pages-list");
  el.innerHTML = pageNames
    .map(
      (name, i) => `
    <div class="page-input-row">
      <input class="form-control-premium" type="text" value="${window.GenerationCommon.escapeHtml(name)}" maxlength="100" placeholder="${i === 0 ? "Home" : "Page name"}" data-page-input />
      ${pageNames.length > 1 ? `<button type="button" class="btn-ghost" data-remove-page style="padding:0.4rem 0.6rem;"><i class="bi bi-x-lg"></i></button>` : ""}
    </div>`
    )
    .join("");
  el.querySelectorAll("[data-page-input]").forEach((input, i) => {
    input.addEventListener("input", () => {
      pageNames[i] = input.value;
    });
  });
  el.querySelectorAll("[data-remove-page]").forEach((btn, i) => {
    btn.addEventListener("click", () => {
      pageNames.splice(i, 1);
      renderPagesList();
    });
  });
}

function setSiteError(field, message) {
  const el = document.querySelector(`[data-error-for="${field}"]`);
  if (!el) return;
  el.textContent = message || "";
  el.classList.toggle("visible", Boolean(message));
}

function renderDeployArea(website) {
  const el = document.getElementById("site-deploy-area");
  if (!el) return;
  if (website.deployment_provider) {
    el.innerHTML = website.deployment_live_url
      ? `<div class="d-flex align-items-center gap-2">
          <span class="badge-pill badge-success"><span class="dot dot-success"></span> Deployed</span>
          <a href="${website.deployment_live_url}" target="_blank" rel="noopener" class="btn-brand" style="padding:0.4rem 0.9rem; font-size:0.82rem;"><i class="bi bi-box-arrow-up-right"></i> Open live site</a>
        </div>`
      : `<div class="d-flex align-items-center gap-2">
          <span class="badge-pill badge-success"><span class="dot dot-success"></span> Deployed</span>
          <a href="${downloadDeploymentUrl(website.id)}" target="_blank" rel="noopener" class="btn-brand" style="padding:0.4rem 0.9rem; font-size:0.82rem;"><i class="bi bi-download"></i> Download .zip</a>
        </div>`;
    return;
  }
  el.innerHTML = `<button type="button" class="btn-brand" id="site-deploy-btn"><i class="bi bi-cloud-arrow-up"></i> Deploy website</button>`;
  document.getElementById("site-deploy-btn").addEventListener("click", deployWebsite);
}

async function deployWebsite() {
  const btn = document.getElementById("site-deploy-btn");
  const originalLabel = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Deploying…`;
  try {
    await window.AIAgentApi.post(`/websites/${currentWebsite.id}/deploy`, {});
    currentWebsite = await window.AIAgentApi.get(`/websites/${currentWebsite.id}`);
    renderDeployArea(currentWebsite);
    window.AIAgentToast.show("Website deployed.", "success");
    await loadSites();
  } catch (err) {
    window.AIAgentToast.show(err.message, "error");
    btn.disabled = false;
    btn.innerHTML = originalLabel;
  }
}

function renderWebsiteResult(website) {
  currentWebsite = website;
  document.getElementById("site-empty-state").classList.add("d-none");
  const panel = document.getElementById("site-result-panel");
  panel.style.display = "";
  document.getElementById("site-result-status").innerHTML = window.GenerationCommon.jobStatusBadge(website.status);

  const body = document.getElementById("site-result-body");
  if (website.status === "failed" || !website.pages.length) {
    body.innerHTML = `<div class="alert-inline visible error">${window.GenerationCommon.escapeHtml(website.error || "This website could not be generated.")}</div>`;
    return;
  }

  const tabsHtml = website.pages
    .map(
      (p, i) => `<button type="button" class="website-page-tab ${i === 0 ? "active" : ""}" data-path="${window.GenerationCommon.escapeHtml(p.path)}">${window.GenerationCommon.escapeHtml(p.name)}</button>`
    )
    .join("");
  const firstPath = website.pages[0].path;

  body.innerHTML = `
    <div class="website-page-tabs">${tabsHtml}</div>
    <div class="website-browser-frame mb-3">
      <div class="website-browser-chrome">
        <span class="dot"></span><span class="dot"></span><span class="dot"></span>
        <span class="url-bar" id="site-preview-url">${window.GenerationCommon.escapeHtml(firstPath)}</span>
      </div>
      <iframe id="site-preview-iframe" src="${previewUrl(website.id, firstPath)}" title="Website preview"></iframe>
    </div>
    <div id="site-deploy-area"></div>
  `;

  body.querySelectorAll(".website-page-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      body.querySelectorAll(".website-page-tab").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById("site-preview-iframe").src = previewUrl(website.id, btn.dataset.path);
      document.getElementById("site-preview-url").textContent = btn.dataset.path;
    });
  });

  renderDeployArea(website);
}

function renderSiteList() {
  const listEl = document.getElementById("site-list");
  const emptyEl = document.getElementById("site-list-empty");
  emptyEl.querySelector("h6").textContent = "No websites yet";
  emptyEl.querySelector("p").textContent = "Websites you generate will be listed here.";
  if (!siteJobs.length) {
    listEl.innerHTML = "";
    emptyEl.classList.remove("d-none");
    return;
  }
  emptyEl.classList.add("d-none");
  listEl.innerHTML = siteJobs
    .map(
      (w) => `
    <div class="gen-list-row" data-id="${w.id}">
      <div class="gen-thumb d-flex align-items-center justify-content-center"><i class="bi bi-globe" style="color:var(--text-muted);"></i></div>
      <div class="min-width-0 flex-grow-1" style="cursor:pointer;" data-view="${w.id}">
        <div class="gen-title text-truncate">${window.GenerationCommon.escapeHtml(w.name)}</div>
        <div class="gen-meta">${window.GenerationCommon.jobStatusBadge(w.status)} · ${window.GenerationCommon.formatDate(w.created_at)}</div>
      </div>
    </div>`
    )
    .join("");

  listEl.querySelectorAll("[data-view]").forEach((el) => {
    el.addEventListener("click", () => {
      const website = siteJobs.find((w) => w.id === el.dataset.view);
      if (website) renderWebsiteResult(website);
    });
  });
}

async function loadSites() {
  const listEl = document.getElementById("site-list");
  const emptyEl = document.getElementById("site-list-empty");
  try {
    siteJobs = await window.AIAgentApi.get("/websites");
    renderSiteList();
  } catch (err) {
    console.error("[website-generation] Could not load recent generations:", err);
    listEl.innerHTML = "";
    emptyEl.classList.remove("d-none");
    emptyEl.querySelector("h6").textContent = "Unable to load recent generations";
    emptyEl.querySelector("p").textContent = err.message || "Please try again.";
    window.AIAgentToast.show("Could not load your recent websites.", "error");
  }
}

async function loadCapability() {
  try {
    const caps = await window.AIAgentApi.get("/system/capabilities");
    window.GenerationCommon.renderCapabilityBanner("capability-banner", caps.ai);
  } catch (err) {
    console.error("[website-generation] Could not load provider capability:", err);
  }
}

async function generateWebsite() {
  const name = document.getElementById("site-name").value.trim();
  const prompt = document.getElementById("site-prompt").value.trim();
  const projectId = document.getElementById("site-project").value;
  setSiteError("name", "");
  setSiteError("prompt", "");

  let hasError = false;
  if (!name) {
    setSiteError("name", "Give the website a name.");
    hasError = true;
  }
  if (prompt.length < 3) {
    setSiteError("prompt", "Describe the website you want in a bit more detail.");
    hasError = true;
  }
  const cleanedPages = pageNames.map((p) => p.trim()).filter(Boolean);
  if (!cleanedPages.length) {
    window.AIAgentToast.show("Add at least one page.", "error");
    hasError = true;
  }
  if (hasError) return;

  const btn = document.getElementById("site-generate-btn");
  const originalLabel = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Generating…`;

  try {
    const website = await window.AIAgentApi.post("/websites", {
      name,
      prompt,
      style: selectedSiteStyle,
      pages: cleanedPages,
      project_id: projectId || undefined,
    });
    renderWebsiteResult(website);
    await loadSites();
  } catch (err) {
    if (err.status === 422) {
      const fieldError = (err.fieldErrors || [])[0];
      if (fieldError && (fieldError.field === "name" || fieldError.field === "prompt")) {
        setSiteError(fieldError.field, fieldError.message);
      } else {
        window.AIAgentToast.show((fieldError && fieldError.message) || err.message, "error");
      }
    } else if (err.status === 503) {
      // The prompt was still persisted server-side (never lost) — refresh
      // the list so the user can see it recorded as failed, then show it.
      await loadSites();
      const latest = siteJobs[0];
      if (latest) renderWebsiteResult(latest);
      window.AIAgentToast.show(err.message, "error");
    } else {
      window.AIAgentToast.show(err.message, "error");
    }
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalLabel;
  }
}

async function init() {
  let user;
  try {
    user = await window.AppShell.initAppShell("website");
  } catch (err) {
    console.error("[website-generation] Failed to initialize app shell:", err);
    window.AIAgentToast.show("Could not load the application shell. Please refresh the page.", "error");
    return;
  }
  if (!user) return;

  try {
    const styleParam = new URLSearchParams(window.location.search).get("style");
    if (styleParam && SITE_STYLES.some((s) => s.key === styleParam)) {
      selectedSiteStyle = styleParam;
    }
    renderStylePicker();
    document.getElementById("site-3d-note").classList.toggle("d-none", selectedSiteStyle !== "3d");
    renderPagesList();
    document.getElementById("site-add-page-btn").addEventListener("click", () => {
      if (pageNames.length >= 12) return;
      pageNames.push("");
      renderPagesList();
    });
    document.getElementById("site-generate-btn").addEventListener("click", generateWebsite);

    await Promise.all([loadCapability(), window.GenerationCommon.loadProjectOptions("site-project"), loadSites()]);
  } catch (err) {
    console.error("[website-generation] Unexpected error during page initialization:", err);
    window.AIAgentToast.show("Something went wrong loading this page. Please refresh and try again.", "error");
  }
}

init();
