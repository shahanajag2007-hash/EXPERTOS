import { clientId, saveSession, sessionToken } from "./identity";

// Base URL of the Flask backend. Override with VITE_API_URL in frontend/.env.
export const API = (import.meta.env.VITE_API_URL || "http://127.0.0.1:5000").replace(/\/$/, "");

export const BACKEND_UNAVAILABLE =
  "Can't reach the ExpertOS consultation service. Make sure the backend is running, then try again.";

// The product's response-time target; after this the UI says the request is
// taking longer than usual (it keeps waiting).
export const SLOW_RESPONSE_MS = 30000;

// Hard limit for streamed requests before the UI gives up.
export const STREAM_TIMEOUT_MS = 150000;

const TOKEN_HEADER = "X-Consultation-Token";

/** An error with the backend's message plus whether retrying can help. */
export class ApiError extends Error {
  constructor(message, { status, code, retryable = false, fields, retryAt = null, providers = [] } = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.retryable = retryable;
    this.fields = fields;
    // When an AI provider expects to accept requests again (Date), if reported.
    this.retryAt = retryAt;
    // Providers tried and why each failed: [{ provider, category, skipped }].
    this.providers = providers;
  }
}

function headers(token, json = true) {
  const h = { "X-Client-Id": clientId() };
  if (json) h["Content-Type"] = "application/json";
  if (token) h[TOKEN_HEADER] = token;
  const session = sessionToken();
  if (session) h.Authorization = `Bearer ${session}`;
  return h;
}

// The backend rejects an expired or revoked session with code "unauthorized";
// forget it so the next request is made as this browser instead.
function handleUnauthorized(status, data) {
  if (status === 401 && data?.code === "unauthorized" && sessionToken()) saveSession(null);
}

async function request(method, path, { body, token, signal } = {}) {
  let res;

  try {
    res = await fetch(`${API}${path}`, {
      method,
      headers: headers(token, body !== undefined),
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal,
    });
  } catch (err) {
    if (err?.name === "AbortError") throw err;
    throw new ApiError(BACKEND_UNAVAILABLE, { code: "connection", retryable: true });
  }

  let data = null;

  try {
    data = await res.json();
  } catch {
    // Not JSON (e.g. a proxy error page); handled below.
  }

  if (!res.ok || data === null) {
    handleUnauthorized(res.status, data);
    throw new ApiError(
      data?.error || `The consultation service returned an error (${res.status}). Please try again.`,
      {
        status: res.status,
        code: data?.code,
        retryable: data?.retryable ?? res.status >= 500,
        fields: data?.fields,
        retryAt: parseRetryAt(data?.retry_at),
        providers: data?.providers || [],
      },
    );
  }

  return data;
}

/**
 * POST JSON to the backend and return the parsed response.
 * Throws an ApiError with a user-readable message for network failures,
 * non-JSON responses and error status codes.
 */
export function postJSON(path, body, options = {}) {
  return request("POST", path, { ...options, body });
}

export function getJSON(path, options = {}) {
  return request("GET", path, options);
}

export function deleteJSON(path, options = {}) {
  return request("DELETE", path, options);
}

/**
 * POST multipart form data (file uploads) and return the parsed response.
 * Uses XMLHttpRequest so upload progress can be reported:
 * onProgress(fraction 0..1). Pass `signal` to cancel.
 */
export function postForm(path, formData, { onProgress, signal } = {}) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API}${path}`);
    const h = headers(null, false);
    Object.entries(h).forEach(([key, value]) => xhr.setRequestHeader(key, value));

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress?.(e.loaded / e.total);
    };
    xhr.onerror = () => reject(new ApiError(BACKEND_UNAVAILABLE, { code: "connection", retryable: true }));
    xhr.onabort = () => reject(new DOMException("Upload cancelled", "AbortError"));
    xhr.onload = () => {
      let data = null;
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        // handled below
      }
      if (xhr.status >= 200 && xhr.status < 300 && data) {
        resolve(data);
        return;
      }
      handleUnauthorized(xhr.status, data);
      reject(new ApiError(data?.error || `The upload failed (${xhr.status}). Please try again.`, {
        status: xhr.status,
        code: data?.code,
        retryable: data?.retryable ?? xhr.status >= 500,
      }));
    };
    signal?.addEventListener("abort", () => xhr.abort());
    xhr.send(formData);
  });
}

/**
 * POST to a server-sent-events endpoint and call onEvent(name, data) for each
 * event as it arrives. Resolves when the stream ends.
 *
 * - Validation errors (normal JSON responses) throw ApiError before any event.
 * - An "error" event from the server is thrown as ApiError.
 * - onSlow() is called once if no event has arrived after SLOW_RESPONSE_MS.
 * - The request is aborted after timeoutMs; pass `signal` to cancel earlier.
 */
export async function streamSSE(path, body, { token, onEvent, onSlow, signal, timeoutMs = STREAM_TIMEOUT_MS } = {}) {
  const controller = new AbortController();
  let timedOut = false;

  const abortFromCaller = () => controller.abort();
  signal?.addEventListener("abort", abortFromCaller);

  const slowTimer = onSlow ? setTimeout(onSlow, SLOW_RESPONSE_MS) : null;
  const hardTimer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);

  const cleanup = () => {
    clearTimeout(slowTimer);
    clearTimeout(hardTimer);
    signal?.removeEventListener("abort", abortFromCaller);
  };

  let res;

  try {
    res = await fetch(`${API}${path}`, {
      method: "POST",
      headers: { ...headers(token), Accept: "text/event-stream" },
      body: JSON.stringify(body ?? {}),
      signal: controller.signal,
    });
  } catch (err) {
    cleanup();
    if (timedOut) throw timeoutError();
    if (err?.name === "AbortError") throw err;
    throw new ApiError(BACKEND_UNAVAILABLE, { code: "connection", retryable: true });
  }

  if (!res.ok || !(res.headers.get("Content-Type") || "").includes("text/event-stream")) {
    cleanup();
    let data = null;
    try {
      data = await res.json();
    } catch {
      // ignored
    }
    handleUnauthorized(res.status, data);
    throw new ApiError(data?.error || `The consultation service returned an error (${res.status}).`, {
      status: res.status,
      code: data?.code,
      retryable: data?.retryable ?? res.status >= 500,
    });
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let boundary;
      while ((boundary = buffer.indexOf("\n\n")) !== -1) {
        const block = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);

        const parsed = parseEvent(block);
        if (!parsed) continue;

        clearTimeout(slowTimer);

        if (parsed.event === "error") {
          throw new ApiError(parsed.data.error || "The request failed. Please try again.", {
            code: parsed.data.code,
            retryable: Boolean(parsed.data.retryable),
            retryAt: parseRetryAt(parsed.data.retry_at),
            providers: parsed.data.providers || [],
          });
        }

        onEvent?.(parsed.event, parsed.data);
      }
    }
  } catch (err) {
    if (timedOut) throw timeoutError();
    if (err instanceof ApiError || err?.name === "AbortError") throw err;
    throw new ApiError("The connection was interrupted. Please try again.", {
      code: "connection",
      retryable: true,
    });
  } finally {
    cleanup();
  }
}

function parseRetryAt(value) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function timeoutError() {
  return new ApiError("The experts took too long to respond. Please try again.", {
    code: "timeout",
    retryable: true,
  });
}

function parseEvent(block) {
  let event = "message";
  const data = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
  }
  if (data.length === 0) return null;
  try {
    return { event, data: JSON.parse(data.join("\n")) };
  } catch {
    return null;
  }
}
