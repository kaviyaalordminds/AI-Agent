/* Shared application shell: sidebar navigation, topbar, auth guard, and
 * logout — used by every authenticated page so the nav markup exists in one
 * place. Items with `enabled: false` are real, honest "not built yet"
 * placeholders (per the phased roadmap) — they are visibly disabled and
 * explain themselves on click rather than pretending to work. */

const NAV_STRUCTURE = [
  {
    label: "Shadow AI",
    items: [
      { key: "dashboard", label: "Home", icon: "bi-house", href: "dashboard.html", enabled: true },
      { key: "agent", label: "AI Chat", icon: "bi-chat-dots", href: "agent.html", enabled: true },
    ],
  },
  {
    label: "Create",
    items: [
      { key: "image", label: "Image", icon: "bi-image", href: "image-generation.html", enabled: true },
      { key: "audio-generation", label: "Audio", icon: "bi-mic", href: "audio-generation.html", enabled: true },
      { key: "audio-transcription", label: "Audio Transcription", icon: "bi-file-earmark-text", href: "audio-transcription.html", enabled: true },
      { key: "audio-cloning", label: "Audio Cloning", icon: "bi-person-vcard", href: "audio-cloning.html", enabled: true },
      { key: "video", label: "Video", icon: "bi-camera-reels", href: "video-generation.html", enabled: true },
      { key: "documents", label: "Documents", icon: "bi-file-earmark-text", href: "documents.html", enabled: true },
      { key: "word", label: "Word Docs", icon: "bi-file-earmark-word", href: "word-generation.html", enabled: true },
      { key: "excel", label: "Spreadsheets", icon: "bi-file-earmark-spreadsheet", href: "excel-generation.html", enabled: true },
      { key: "presentations", label: "Presentations", icon: "bi-easel", href: "ppt-generation.html", enabled: true },
      { key: "website", label: "Website", icon: "bi-globe", href: "website-generation.html", enabled: true },
      { key: "website3d", label: "3D Website", icon: "bi-badge-3d", href: "website-generation.html?style=3d", enabled: true },
      { key: "poster", label: "Poster", icon: "bi-file-earmark-image", href: "poster-generation.html", enabled: true },
      { key: "logo", label: "Logo", icon: "bi-vector-pen", href: "logo-generation.html", enabled: true },
      { key: "design", label: "Graphic Design", icon: "bi-palette", href: "graphic-design-generation.html", enabled: true },
    ],
  },
  {
    label: "Projects",
    items: [{ key: "projects", label: "Projects", icon: "bi-kanban", href: "projects.html", enabled: true }],
  },
  {
    label: "Knowledge",
    items: [
      { key: "knowledge", label: "Knowledge Center", icon: "bi-diagram-3", href: "knowledge.html", enabled: true },
      { key: "knowledge-gaps", label: "Knowledge Gaps", icon: "bi-search", href: "knowledge-gaps.html", enabled: true },
      { key: "knowledge-updates", label: "Knowledge Updates", icon: "bi-arrow-repeat", href: "history.html?type=knowledge_update", enabled: true },
      { key: "obsidian", label: "Obsidian", icon: "bi-safe2", href: "obsidian.html", enabled: true },
    ],
  },
  {
    label: "History",
    items: [{ key: "history", label: "History", icon: "bi-clock-history", href: "history.html", enabled: true }],
  },
  {
    label: "Deployments",
    items: [{ key: "deployments", label: "Deployments", icon: "bi-cloud-arrow-up", href: "#", enabled: false }],
  },
  {
    label: "Settings",
    items: [
      { key: "system-status", label: "System Status", icon: "bi-activity", href: "system-status.html", enabled: true },
      { key: "settings", label: "Settings", icon: "bi-gear", href: "settings.html", enabled: true },
      { key: "profile", label: "Profile", icon: "bi-person-circle", href: "profile.html", enabled: true },
    ],
  },
];

function renderNavItem(item, activeKey) {
  const isActive = item.key === activeKey;
  const classes = ["nav-link-item"];
  if (isActive) classes.push("active");
  if (!item.enabled) classes.push("disabled");
  const badge = !item.enabled ? '<span class="nav-link-badge">Soon</span>' : "";
  const tag = item.enabled ? "a" : "div";
  const hrefAttr = item.enabled ? `href="${item.href}"` : "";
  return `<${tag} ${hrefAttr} class="${classes.join(" ")}" data-nav-key="${item.key}" data-enabled="${item.enabled}">
    <i class="bi ${item.icon}"></i><span class="nav-link-label">${item.label}</span>${badge}
  </${tag}>`;
}

function renderSidebarHtml(activeKey) {
  const groups = NAV_STRUCTURE.map(
    (group) => `
    <div class="nav-group-label">${group.label}</div>
    ${group.items.map((item) => renderNavItem(item, activeKey)).join("")}
  `
  ).join("");

  return `
    <div class="sidebar-brand">
      <span class="glyph"><i class="bi bi-stars"></i></span>
      <span class="nav-link-label">Shadow AI</span>
    </div>
    <nav>${groups}</nav>
    <div class="sidebar-footer">
      <button type="button" class="sidebar-collapse-btn" id="sidebar-collapse-toggle" title="Collapse sidebar">
        <i class="bi bi-layout-sidebar-inset"></i>
      </button>
    </div>
  `;
}

function initials(name) {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0].toUpperCase())
    .join("");
}

function formatDateTime(iso) {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function describeUserAgent(ua) {
  if (!ua) return "Unknown device";
  let browser = "Unknown browser";
  if (/edg/i.test(ua)) browser = "Edge";
  else if (/chrome|chromium|crios/i.test(ua)) browser = "Chrome";
  else if (/firefox|fxios/i.test(ua)) browser = "Firefox";
  else if (/safari/i.test(ua)) browser = "Safari";

  let os = "Unknown OS";
  if (/windows/i.test(ua)) os = "Windows";
  else if (/mac os/i.test(ua)) os = "macOS";
  else if (/android/i.test(ua)) os = "Android";
  else if (/iphone|ipad|ios/i.test(ua)) os = "iOS";
  else if (/linux/i.test(ua)) os = "Linux";

  return `${browser} on ${os}`;
}

function renderSessions(sessions, containerId = "sessions-list") {
  const container = document.getElementById(containerId);
  if (!container) return;
  if (!sessions.length) {
    container.innerHTML = `<div class="empty-state" style="padding:1.5rem 0;"><p class="mb-0">No active sessions.</p></div>`;
    return;
  }
  container.innerHTML = sessions
    .map(
      (s) => `
    <div class="session-row" data-session-id="${s.id}">
      <div>
        <div style="font-size:0.88rem; font-weight:600;">
          ${s.is_current ? '<span class="badge-pill badge-success">This device</span>' : describeUserAgent(s.user_agent)}
        </div>
        <div style="font-size:0.76rem; color:var(--text-muted);">
          Last active ${formatDateTime(s.last_active_at)} · ${s.ip_address || "unknown IP"}
        </div>
      </div>
      ${s.is_current ? "" : `<button type="button" class="btn-ghost revoke-session-btn" style="font-size:0.78rem; padding:0.4rem 0.8rem;">Revoke</button>`}
    </div>`
    )
    .join("");

  container.querySelectorAll(".revoke-session-btn").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      const row = e.target.closest(".session-row");
      const sessionId = row.dataset.sessionId;
      try {
        await window.AIAgentApi.del(`/auth/sessions/${sessionId}`);
        window.AIAgentToast.show("Session revoked.", "success");
        loadSessions(containerId);
      } catch (err) {
        window.AIAgentToast.show(err.message, "error");
      }
    });
  });
}

async function loadSessions(containerId = "sessions-list") {
  const container = document.getElementById(containerId);
  if (!container) return;
  try {
    const sessions = await window.AIAgentApi.get("/auth/sessions");
    renderSessions(sessions, containerId);
  } catch (err) {
    container.innerHTML = `<div class="empty-state"><p>${err.message}</p></div>`;
  }
}

async function logout() {
  try {
    await window.AIAgentApi.post("/auth/logout", {});
  } catch {
    // Even if the network call fails, drop the client back to login —
    // the cookie will simply expire server-side.
  }
  window.location.href = "login.html";
}

// Single source of truth for sidebar collapse state, shared by the sidebar's
// own toggle button (nav.js) and the Settings page checkbox — both call this
// instead of maintaining their own DOM/localStorage/backend copies.
function isSidebarCollapsed() {
  return localStorage.getItem("aiagent:sidebar-collapsed") === "1";
}

function applySidebarCollapsed(collapsed) {
  const shell = document.querySelector(".app-shell");
  if (shell) shell.classList.toggle("sidebar-collapsed", collapsed);
  localStorage.setItem("aiagent:sidebar-collapsed", collapsed ? "1" : "0");
  const settingsToggle = document.getElementById("sidebar-collapsed-toggle");
  if (settingsToggle) settingsToggle.checked = collapsed;
}

async function initAppShell(activeKey) {
  let user;
  try {
    user = await window.AIAgentApi.get("/users/me");
  } catch (err) {
    // Covers both "not logged in" (401) and a hung/unreachable backend
    // (the request now times out after 20s rather than hanging forever
    // — see api.js) — either way, never leave the page stuck on
    // "Loading…"; send the user somewhere actionable instead.
    console.error("[nav] Could not load the current user, redirecting to login:", err);
    window.location.href = `login.html?session_expired=1`;
    return null;
  }

  const shell = document.querySelector(".app-shell");
  const sidebarMount = document.getElementById("app-sidebar");
  sidebarMount.innerHTML = renderSidebarHtml(activeKey);

  document.querySelectorAll('[data-enabled="false"]').forEach((el) => {
    el.addEventListener("click", (e) => {
      e.preventDefault();
      window.AIAgentToast.show(
        `${el.querySelector(".nav-link-label").textContent} is planned for a later development phase.`,
        "info"
      );
    });
  });

  applySidebarCollapsed(isSidebarCollapsed());
  document.getElementById("sidebar-collapse-toggle").addEventListener("click", () => {
    applySidebarCollapsed(!shell.classList.contains("sidebar-collapsed"));
  });

  const userNameEl = document.getElementById("topbar-user-name");
  const userEmailEl = document.getElementById("topbar-user-email");
  const userAvatarEl = document.getElementById("topbar-user-avatar");
  if (userNameEl) userNameEl.textContent = user.full_name;
  if (userEmailEl) userEmailEl.textContent = user.email;
  if (userAvatarEl) userAvatarEl.textContent = initials(user.full_name);

  const logoutBtn = document.getElementById("topbar-logout-btn");
  if (logoutBtn) logoutBtn.addEventListener("click", logout);

  const mobileToggle = document.getElementById("mobile-sidebar-toggle");
  if (mobileToggle) {
    mobileToggle.addEventListener("click", () => sidebarMount.classList.toggle("mobile-open"));
  }

  return user;
}

window.AppShell = {
  initAppShell,
  logout,
  loadSessions,
  renderSessions,
  formatDateTime,
  isSidebarCollapsed,
  applySidebarCollapsed,
};
