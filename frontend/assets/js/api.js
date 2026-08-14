/* Thin fetch wrapper: attaches credentials + CSRF header, parses the
 * backend's error envelope into readable messages, and never pretends a
 * failed request succeeded. Every request carries a hard timeout so a
 * hung backend/network surfaces as a clear error instead of leaving a
 * page stuck in "Loading…" forever. */
const CSRF_COOKIE_NAME = "aiagent_csrf";
const DEFAULT_TIMEOUT_MS = 20000;

function readCookie(name) {
  const match = document.cookie.match(new RegExp("(^|;\\s*)" + name + "=([^;]*)"));
  return match ? decodeURIComponent(match[2]) : null;
}

class ApiError extends Error {
  constructor(message, status, fieldErrors) {
    super(message);
    this.status = status;
    this.fieldErrors = fieldErrors || [];
  }
}

async function apiRequest(path, { method = "GET", body, headers = {}, timeoutMs = DEFAULT_TIMEOUT_MS } = {}) {
  const isUnsafe = method !== "GET" && method !== "HEAD";
  const finalHeaders = { ...headers };
  if (body !== undefined) finalHeaders["Content-Type"] = "application/json";
  if (isUnsafe) {
    const csrf = readCookie(CSRF_COOKIE_NAME);
    if (csrf) finalHeaders["X-CSRF-Token"] = csrf;
  }

  const controller = new AbortController();
  const timeoutId = timeoutMs ? setTimeout(() => controller.abort(), timeoutMs) : null;

  let response;
  try {
    response = await fetch(`${window.AIAgentConfig.apiBase}${path}`, {
      method,
      credentials: "include",
      headers: finalHeaders,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
  } catch (networkError) {
    const message =
      networkError && networkError.name === "AbortError"
        ? "The server took too long to respond. Please try again."
        : "Could not reach the server. Check your connection and that the backend is running.";
    console.error(`[api] ${method} ${path} failed:`, networkError);
    throw new ApiError(message, 0);
  } finally {
    if (timeoutId) clearTimeout(timeoutId);
  }

  let data = null;
  const text = await response.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }

  if (!response.ok) {
    const message = (data && data.detail) || `Request failed (${response.status}).`;
    console.error(`[api] ${method} ${path} -> ${response.status}: ${message}`);
    throw new ApiError(message, response.status, (data && data.errors) || []);
  }

  return data;
}

window.AIAgentApi = {
  get: (path, options) => apiRequest(path, { method: "GET", ...options }),
  post: (path, body, options) => apiRequest(path, { method: "POST", body, ...options }),
  patch: (path, body, options) => apiRequest(path, { method: "PATCH", body, ...options }),
  del: (path, options) => apiRequest(path, { method: "DELETE", ...options }),
  getCsrfToken: () => readCookie(CSRF_COOKIE_NAME),
  apiBase: () => window.AIAgentConfig.apiBase,
  ApiError,
};
