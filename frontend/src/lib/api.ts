import type { Envelope, Problem } from "@/types/api";

const BASE = `${import.meta.env.VITE_API_URL ?? ""}/api/v1`;
const TIMEOUT_MS = 20_000;

/** Structured API failure. `offline` is true when the server could not be reached at all. */
export class ApiClientError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | null;
  readonly offline: boolean;
  readonly problem: Problem | null;

  constructor(message: string, opts: { status: number; code: string; requestId?: string | null; offline?: boolean; problem?: Problem | null }) {
    super(message);
    this.name = "ApiClientError";
    this.status = opts.status;
    this.code = opts.code;
    this.requestId = opts.requestId ?? null;
    this.offline = opts.offline ?? false;
    this.problem = opts.problem ?? null;
  }
}

let apiKey: string | null = null;
/** API key is kept in memory only (never persisted). */
export function setApiKey(key: string | null): void {
  apiKey = key && key.trim() ? key.trim() : null;
}
export function getApiKey(): string | null {
  return apiKey;
}

type Params = Record<string, string | number | boolean | null | undefined>;

export function buildUrl(path: string, params?: Params): string {
  const url = new URL(`${BASE}${path}`, window.location.origin);
  for (const [k, v] of Object.entries(params ?? {})) {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
  }
  return url.pathname + url.search;
}

async function send(path: string, init: RequestInit & { params?: Params } = {}): Promise<Response> {
  const ctrl = new AbortController();
  const timer = window.setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (apiKey) headers.set("X-API-Key", apiKey);
  try {
    const res = await fetch(buildUrl(path, init.params), { ...init, headers, signal: ctrl.signal });
    if (!res.ok) {
      let problem: Problem | null = null;
      try {
        problem = (await res.json()) as Problem;
      } catch {
        problem = null;
      }
      throw new ApiClientError(problem?.title ?? `HTTP ${res.status}`, {
        status: res.status,
        code: problem?.code ?? `HTTP_${res.status}`,
        requestId: problem?.request_id ?? res.headers.get("X-Request-ID"),
        problem,
      });
    }
    return res;
  } catch (err) {
    if (err instanceof ApiClientError) throw err;
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiClientError("The request timed out", { status: 0, code: "TIMEOUT" });
    }
    throw new ApiClientError("The API could not be reached", { status: 0, code: "OFFLINE", offline: true });
  } finally {
    window.clearTimeout(timer);
  }
}

export async function apiGet<T>(path: string, params?: Params): Promise<Envelope<T>> {
  return (await send(path, { method: "GET", params })).json() as Promise<Envelope<T>>;
}

export async function apiPost<T>(path: string, body: unknown): Promise<Envelope<T>> {
  const res = await send(path, { method: "POST", body: JSON.stringify(body), headers: { "Content-Type": "application/json" } });
  return res.json() as Promise<Envelope<T>>;
}

/** Download an API resource as a file (works with the API-key header, unlike a plain link). */
export async function downloadResource(path: string, filename: string): Promise<void> {
  const res = await send(path);
  const blob = await res.blob();
  const href = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = href;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(href);
}

export function wsUrl(channels = "events,alerts,jobs"): string {
  const base = import.meta.env.VITE_API_URL ? new URL(import.meta.env.VITE_API_URL as string) : new URL(window.location.origin);
  base.protocol = base.protocol === "https:" ? "wss:" : "ws:";
  return `${base.origin}/api/v1/ws?channels=${encodeURIComponent(channels)}`;
}
