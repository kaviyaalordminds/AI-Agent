/* Single source of truth for where the backend API lives. Override by
 * setting `window.__AIAGENT_API_BASE__` before this script loads (e.g. in a
 * deployment-specific script tag) if the frontend is served from a
 * different origin than the backend's default dev port (8000).
 *
 * Derived from window.location.hostname rather than hardcoded, and this
 * matters for a real, previously-hit bug: session cookies are
 * SameSite=Lax (see app/security/sessions.py), and "localhost" /
 * "127.0.0.1" are different *sites* for cookie purposes even though both
 * point at the same machine. A hardcoded apiBase that doesn't match
 * whatever hostname the page was actually opened from turns every API
 * call into a cross-site request: the browser silently accepts the
 * Set-Cookie on login, then refuses to attach that cookie on the very
 * next request, so login appears to succeed but the following
 * GET /api/users/me comes back 401 and the user is bounced straight back
 * to the login page. Deriving apiBase from the page's own hostname makes
 * this impossible to get wrong: open the app at localhost:5173 and it
 * calls localhost:8000; open it at 127.0.0.1:5173 and it calls
 * 127.0.0.1:8000 — always same-site. The backend's CORS allow-list
 * (app/core/config.py: resolved_cors_origins) trusts both hostnames on
 * FRONTEND_URL's port for exactly this reason. */
window.AIAgentConfig = {
  apiBase: window.__AIAGENT_API_BASE__ || `${window.location.protocol}//${window.location.hostname}:8000/api`,
  /* AI_PROVIDER is configurable server-side (anthropic/gemini) — never
   * hard-code "Claude" in status text, since Gemini is also a valid
   * choice for chat/reasoning. */
  aiProviderLabel(providerKey) {
    const labels = { anthropic: "Claude", gemini: "Gemini" };
    return labels[providerKey] || providerKey || "AI provider";
  },
};
