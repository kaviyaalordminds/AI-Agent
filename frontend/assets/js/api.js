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

  // A fresh controller per call — never shared/reused across requests —
  // so aborting one request (timeout or otherwise) can never affect any
  // other in-flight or future request.
  const controller = new AbortController();
  // Tag *why* we aborted so the catch block below can tell "our own
  // timeout fired" apart from any other abort reason (e.g. the browser
  // cancelling in-flight fetches on page navigation) instead of lumping
  // every AbortError under the same generic message.
  const timeoutId = timeoutMs
    ? setTimeout(() => controller.abort(new DOMException("Request timed out", "TimeoutError")), timeoutMs)
    : null;

  const requestStartedAt = performance.now();
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
    const elapsedMs = Math.round(performance.now() - requestStartedAt);
    const isOurTimeout = controller.signal.aborted && controller.signal.reason && controller.signal.reason.name === "TimeoutError";
    let message;
    if (isOurTimeout) {
      // C) Genuine timeout: our own AbortController fired because the
      // configured timeoutMs elapsed with no response at all.
      message = `The server took too long to respond (waited ${Math.round(timeoutMs / 1000)}s). Please try again.`;
    } else if (networkError && networkError.name === "AbortError") {
      // D) Some other abort (not our timeout) — most commonly the
      // browser cancelling this fetch because the page navigated away.
      // Never mislabel this as a server-side timeout.
      message = "The request was interrupted. Please try again.";
    } else {
      // B) A real network-level failure — the request never reached (or
      // never got a response from) the backend at all.
      message = "Could not reach the server. Check your connection and that the backend is running.";
    }
    console.error(
      `[api] ${method} ${path} failed after ${elapsedMs}ms (${isOurTimeout ? "timeout" : networkError && networkError.name}):`,
      networkError
    );
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
