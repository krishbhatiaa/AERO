import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { create } from "zustand";

import { getApiKey, wsUrl } from "@/lib/api";
import type { WsMessage } from "@/types/api";

export type LiveStatus = "connecting" | "open" | "closed";
interface LiveState {
  status: LiveStatus;
  lastMessage: WsMessage | null;
  jobProgress: Record<string, { step: string; fraction: number; status?: string }>;
  set: (p: Partial<Pick<LiveState, "status" | "lastMessage">>) => void;
  progress: (jobId: string, step: string, fraction: number, status?: string) => void;
}
export const useLive = create<LiveState>((set) => ({
  status: "closed",
  lastMessage: null,
  jobProgress: {},
  set: (p) => set(p),
  progress: (jobId, step, fraction, status) => set((s) => ({ jobProgress: { ...s.jobProgress, [jobId]: { step, fraction, status } } })),
}));

/** One app-wide WebSocket with exponential-backoff reconnect. Updates panels without page reloads. */
export function useLiveConnection(enabled = true): void {
  const qc = useQueryClient();
  useEffect(() => {
    if (!enabled || typeof WebSocket === "undefined") return;
    let ws: WebSocket | null = null;
    let timer: number | undefined;
    let attempt = 0;
    let stopped = false;

    const connect = (): void => {
      useLive.getState().set({ status: "connecting" });
      ws = new WebSocket(wsUrl());
      ws.onopen = () => {
        attempt = 0;
        const key = getApiKey();
        if (key) ws?.send(JSON.stringify({ type: "auth", api_key: key }));
        useLive.getState().set({ status: "open" });
      };
      ws.onmessage = (ev: MessageEvent<string>) => {
        let msg: WsMessage;
        try {
          msg = JSON.parse(ev.data) as WsMessage;
        } catch {
          return;
        }
        useLive.getState().set({ lastMessage: msg });
        const p = msg.payload;
        if (msg.type === "job.progress" && p.job_id) useLive.getState().progress(p.job_id, String(p.step ?? ""), Number(p.fraction ?? 0));
        if (msg.type === "job.finished" && p.job_id) {
          useLive.getState().progress(p.job_id, "done", 1, String(p.status ?? ""));
          void qc.invalidateQueries();
        }
        if (msg.type === "event.updated" || msg.type === "alert.created") void qc.invalidateQueries();
      };
      ws.onclose = () => {
        useLive.getState().set({ status: "closed" });
        if (stopped) return;
        attempt += 1;
        timer = window.setTimeout(connect, Math.min(15_000, 500 * 2 ** attempt));
      };
      ws.onerror = () => ws?.close();
    };
    connect();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
      ws?.close();
    };
  }, [enabled, qc]);
}
