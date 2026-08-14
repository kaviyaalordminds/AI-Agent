/* Single source of truth for where the backend API lives. Override by
 * setting `window.__AIAGENT_API_BASE__` before this script loads (e.g. in a
 * deployment-specific script tag) if the frontend is served from a
 * different origin than http://localhost:8000.
 *
 * MUST use the same hostname ("localhost") the frontend itself is
 * served from, NOT "127.0.0.1" — this was tried and reverted. Session
 * cookies are set with SameSite=Lax (see app/security/sessions.py), and
 * "localhost" and "127.0.0.1" are different *sites* for cookie purposes
 * even though both point at the same machine. Pointing this at
 * 127.0.0.1 while the page itself loads from http://localhost:5173
 * turns every API call into a cross-site request: the browser silently
 * accepts the Set-Cookie on login, then refuses to attach that cookie
 * on the very next request, so login appears to succeed but the
 * following GET /api/users/me comes back 401 and the user is bounced
 * straight back to the login page. Keep this hostname identical to
 * whatever host you actually open the frontend at. */
window.AIAgentConfig = {
  apiBase: window.__AIAGENT_API_BASE__ || "http://localhost:8000/api",
  /* AI_PROVIDER is configurable server-side (anthropic/gemini) — never
   * hard-code "Claude" in status text, since Gemini is also a valid
   * choice for chat/reasoning. */
  aiProviderLabel(providerKey) {
    const labels = { anthropic: "Claude", gemini: "Gemini" };
    return labels[providerKey] || providerKey || "AI provider";
  },
};
