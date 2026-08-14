/* Single source of truth for where the backend API lives. Override by
 * setting `window.__AIAGENT_API_BASE__` before this script loads (e.g. in a
 * deployment-specific script tag) if the frontend is served from a
 * different origin than http://localhost:8000. */
window.AIAgentConfig = {
  apiBase: window.__AIAGENT_API_BASE__ || "http://localhost:8000/api",
};
