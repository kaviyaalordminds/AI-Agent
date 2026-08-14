/* Single source of truth for where the backend API lives. Override by
 * setting `window.__AIAGENT_API_BASE__` before this script loads (e.g. in a
 * deployment-specific script tag) if the frontend is served from a
 * different origin than http://127.0.0.1:8000.
 *
 * Deliberately 127.0.0.1, not "localhost": on some machines (notably
 * Windows with certain VPN/network-stack configurations) the browser
 * resolving "localhost" can be slow or try IPv6 first and time out before
 * falling back to IPv4, making every API call — including login — take
 * many seconds or appear to hang ("The server took too long to
 * respond."). uvicorn without an explicit --host binds to 127.0.0.1 only
 * (not IPv6 ::1), so targeting it directly skips that resolution
 * entirely. This does not affect CORS: the backend's allow-list is keyed
 * on the frontend's own origin (see FRONTEND_URL in backend/.env), not on
 * what URL the frontend fetches. */
window.AIAgentConfig = {
  apiBase: window.__AIAGENT_API_BASE__ || "http://127.0.0.1:8000/api",
  /* AI_PROVIDER is configurable server-side (anthropic/gemini) — never
   * hard-code "Claude" in status text, since Gemini is also a valid
   * choice for chat/reasoning. */
  aiProviderLabel(providerKey) {
    const labels = { anthropic: "Claude", gemini: "Gemini" };
    return labels[providerKey] || providerKey || "AI provider";
  },
};
