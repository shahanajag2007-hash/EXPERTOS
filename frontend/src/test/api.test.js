import { describe, expect, it, vi } from "vitest";
import { ApiError, streamSSE } from "../services/api";
import { jsonResponse, mockFetch, sse, sseResponse } from "./helpers";

describe("streamSSE", () => {
  it("parses events even when chunks split them", async () => {
    const raw = sse("token", { text: "Hel" }) + sse("token", { text: "lo" }) + sse("done", { reply: "Hello" });
    mockFetch({ "POST /x": sseResponse([raw.slice(0, 7), raw.slice(7, 40), raw.slice(40)]) });

    const events = [];
    await streamSSE("/x", {}, { onEvent: (e, d) => events.push([e, d]) });
    expect(events).toEqual([["token", { text: "Hel" }], ["token", { text: "lo" }], ["done", { reply: "Hello" }]]);
  });

  it("throws server error events as retryable ApiErrors", async () => {
    mockFetch({ "POST /x": sseResponse([sse("token", { text: "Hi" }), sse("error", { error: "Busy", code: "rate_limit", retryable: true })]) });
    const onEvent = vi.fn();
    const err = await streamSSE("/x", {}, { onEvent }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.message).toBe("Busy");
    expect(err.retryable).toBe(true);
    expect(onEvent).toHaveBeenCalledTimes(1);
  });

  it("returns JSON validation errors before streaming", async () => {
    mockFetch({ "POST /x": jsonResponse({ error: "Message cannot be empty." }, 400) });
    const err = await streamSSE("/x", {}).catch((e) => e);
    expect(err.message).toBe("Message cannot be empty.");
    expect(err.status).toBe(400);
  });

  it("reports an unreachable backend clearly", async () => {
    mockFetch({ "POST /x": () => Promise.reject(new TypeError("Failed to fetch")) });
    const err = await streamSSE("/x", {}).catch((e) => e);
    expect(err.message).toMatch(/Can't reach the ExpertOS consultation service/);
    expect(err.retryable).toBe(true);
  });

  it("times out with a clear message", async () => {
    mockFetch({
      "POST /x": (url, options) => new Promise((_, reject) => {
        options.signal.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
      }),
    });
    const err = await streamSSE("/x", {}, { timeoutMs: 20 }).catch((e) => e);
    expect(err.message).toMatch(/took too long/);
    expect(err.code).toBe("timeout");
  });

  it("sends the consultation token as a header, never in the URL", async () => {
    const { calls } = mockFetch({ "POST /x": sseResponse([sse("done", {})]) });
    await streamSSE("/x", {}, { token: "tok" });
    expect(calls[0].options.headers["X-Consultation-Token"]).toBe("tok");
    expect(calls[0].url).not.toContain("tok");
  });
});
