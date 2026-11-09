import { vi } from "vitest";

export function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** A text/event-stream response. `chunks` are raw strings, split anywhere. */
export function sseResponse(chunks) {
  const encoder = new TextEncoder();
  const body = new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
  return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

export const sse = (event, data) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;

/**
 * Mock fetch with a route table: { "GET /stats": handler | response }.
 * Handlers receive (url, options). Unmatched requests fail the test.
 */
export function mockFetch(routes) {
  // Pages with a conversation history list load it on mount; most tests
  // don't care about it, so it defaults to empty.
  routes = { "GET /conversations": jsonResponse({ conversations: [], signed_in: false }), ...routes };
  const calls = [];
  const fetchMock = vi.fn(async (url, options = {}) => {
    const path = new URL(url).pathname;
    const key = `${options.method || "GET"} ${path}`;
    calls.push({ key, url, options, body: options.body ? JSON.parse(options.body) : undefined });
    const route = routes[key];
    if (!route) throw new Error(`Unexpected request: ${key}`);
    return typeof route === "function" ? route(url, options) : route.clone();
  });
  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, calls };
}

export const EMPTY_STATS = {
  completed_consultations: 0,
  active_experts: 6,
  ratings: { total: 0, positive: 0, satisfaction_rate: null, average_stars: null, positive_threshold: 4 },
  response_time: { average_seconds: null, median_seconds: null, samples: 0, target_seconds: 30, window_days: 30, status: "measuring" },
  experts: {},
};
