/* Thin fetch wrapper: attaches credentials + CSRF header, parses the
 * backend's error envelope into readable messages, and never pretends a
 * failed request succeeded. */
const CSRF_COOKIE_NAME = "aiagent_csrf";

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

async function apiRequest(path, { method = "GET", body, headers = {} } = {}) {
  const isUnsafe = method !== "GET" && method !== "HEAD";
  const finalHeaders = { ...headers };
  if (body !== undefined) finalHeaders["Content-Type"] = "application/json";
  if (isUnsafe) {
    const csrf = readCookie(CSRF_COOKIE_NAME);
    if (csrf) finalHeaders["X-CSRF-Token"] = csrf;
  }

  let response;
  try {
    response = await fetch(`${window.AIAgentConfig.apiBase}${path}`, {
      method,
      credentials: "include",
      headers: finalHeaders,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (networkError) {
    throw new ApiError(
      "Could not reach the server. Check your connection and that the backend is running.",
      0
    );
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
    throw new ApiError(message, response.status, (data && data.errors) || []);
  }

  return data;
}

window.AIAgentApi = {
  get: (path) => apiRequest(path, { method: "GET" }),
  post: (path, body) => apiRequest(path, { method: "POST", body }),
  patch: (path, body) => apiRequest(path, { method: "PATCH", body }),
  del: (path) => apiRequest(path, { method: "DELETE" }),
  ApiError,
};
