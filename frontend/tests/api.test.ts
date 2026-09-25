import { apiGet, apiPost, ApiClientError, buildUrl, getApiKey, setApiKey } from "@/lib/api";

const ok = (data: unknown): Response => new Response(JSON.stringify({ data, meta: { request_id: "r1" } }), { status: 200, headers: { "Content-Type": "application/json" } });

afterEach(() => { vi.restoreAllMocks(); setApiKey(null); });

describe("api client", () => {
  it("builds versioned URLs and drops empty params", () => {
    expect(buildUrl("/events", { page: 2, severity: "", x: undefined, y: null })).toBe("/api/v1/events?page=2");
  });
  it("sends the API key header when set and unwraps the envelope", async () => {
    const f = vi.spyOn(globalThis, "fetch").mockResolvedValue(ok({ a: 1 }));
    setApiKey("  secret  ");
    expect(getApiKey()).toBe("secret");
    const r = await apiGet<{ a: number }>("/health");
    expect(r.data.a).toBe(1);
    const headers = (f.mock.calls[0]?.[1] as RequestInit).headers as Headers;
    expect(headers.get("X-API-Key")).toBe("secret");
    expect(headers.get("Accept")).toBe("application/json");
  });
  it("turns problem+json into a structured ApiClientError with the request id", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ type: "t", title: "Event not found", status: 404, code: "EVENT_NOT_FOUND", detail: "No event with id x.", request_id: "req-9" }), { status: 404 }));
    const err = await apiGet("/events/x").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiClientError);
    expect(err).toMatchObject({ status: 404, code: "EVENT_NOT_FOUND", requestId: "req-9", offline: false, message: "Event not found" });
  });
  it("falls back gracefully when an error body is not JSON", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("<html>bad gateway</html>", { status: 502, headers: { "X-Request-ID": "rid" } }));
    await expect(apiGet("/x")).rejects.toMatchObject({ status: 502, code: "HTTP_502", requestId: "rid" });
  });
  it("reports network failure as offline", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(apiGet("/x")).rejects.toMatchObject({ offline: true, code: "OFFLINE" });
  });
  it("reports an aborted request as a timeout", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new DOMException("aborted", "AbortError"));
    await expect(apiGet("/x")).rejects.toMatchObject({ code: "TIMEOUT", offline: false });
  });
  it("posts JSON bodies", async () => {
    const f = vi.spyOn(globalThis, "fetch").mockResolvedValue(ok({ id: "j" }));
    await apiPost("/predictions", { scenario_seed: 3 });
    const init = f.mock.calls[0]?.[1] as RequestInit;
    expect(init.method).toBe("POST");
    expect(init.body).toBe('{"scenario_seed":3}');
    expect((init.headers as Headers).get("Content-Type")).toBe("application/json");
  });
});
