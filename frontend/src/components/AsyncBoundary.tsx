import type { UseQueryResult } from "@tanstack/react-query";
import { CloudOff, Inbox, RefreshCw, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

import { ApiClientError } from "@/lib/api";
import { cn } from "@/lib/utils";

export type AsyncState = "loading" | "success" | "empty" | "partial" | "error" | "offline";

export function deriveState<T>(q: Pick<UseQueryResult<T>, "status" | "error" | "data" | "isPlaceholderData">, isEmpty?: (d: T) => boolean, partial?: boolean): AsyncState {
  if (q.status === "pending") return "loading";
  if (q.status === "error") return q.error instanceof ApiClientError && q.error.offline ? "offline" : "error";
  if (isEmpty && q.data !== undefined && isEmpty(q.data)) return "empty";
  return partial ? "partial" : "success";
}

export function Skeleton({ className }: { className?: string }): JSX.Element {
  return <div aria-hidden className={cn("skeleton h-4 w-full", className)} />;
}

interface Props<T> {
  query: UseQueryResult<T>;
  label: string;
  children: (data: T) => ReactNode;
  isEmpty?: (data: T) => boolean;
  emptyText?: string;
  partialNote?: string | null;
  skeleton?: ReactNode;
  className?: string;
}

/** Renders the six UI states: loading | success | empty | partial | error | offline. */
export function AsyncBoundary<T>({ query, label, children, isEmpty, emptyText, partialNote, skeleton, className }: Props<T>): JSX.Element {
  const state = deriveState(query, isEmpty, !!partialNote);
  const err = query.error instanceof ApiClientError ? query.error : null;
  return (
    <div data-state={state} className={className} aria-live="polite" aria-busy={state === "loading"}>
      {state === "loading" && (
        <div role="status" aria-label={`Loading ${label}`} className="space-y-2 p-1">
          {skeleton ?? (
            <>
              <Skeleton className="h-4 w-2/3" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-5/6" />
            </>
          )}
        </div>
      )}
      {state === "offline" && (
        <div role="alert" className="flex flex-col gap-2 rounded border border-outline-variant bg-surface-container-low p-3 text-on-surface">
          <div className="flex items-center gap-2 font-semibold"><CloudOff aria-hidden className="h-4 w-4" />Offline: the API cannot be reached</div>
          <p className="text-body-sm text-on-surface-variant">{label} could not be loaded. Check that the backend is running; this view will recover automatically.</p>
          <RetryButton onClick={() => void query.refetch()} />
        </div>
      )}
      {state === "error" && (
        <div role="alert" className="flex flex-col gap-2 rounded border border-error/50 bg-error-container/30 p-3 text-on-surface">
          <div className="flex items-center gap-2 font-semibold"><TriangleAlert aria-hidden className="h-4 w-4 text-error" />Could not load {label}</div>
          <p className="text-body-sm text-on-surface-variant">{err?.problem?.detail || err?.message || "Unexpected error"}</p>
          {err?.requestId && <p className="font-mono text-label-num-sm text-on-surface-variant">request id: {err.requestId}</p>}
          <RetryButton onClick={() => void query.refetch()} />
        </div>
      )}
      {state === "empty" && (
        <div className="flex items-center gap-2 rounded border border-dashed border-outline-variant p-3 text-on-surface-variant"><Inbox aria-hidden className="h-4 w-4" />{emptyText ?? `No ${label} to show.`}</div>
      )}
      {(state === "success" || state === "partial") && query.data !== undefined && (
        <>
          {state === "partial" && <div role="note" className="mb-2 rounded border border-sev-moderate/50 bg-sev-moderate/10 px-2 py-1 text-body-xs text-on-surface">Partial data: {partialNote}</div>}
          {children(query.data)}
        </>
      )}
    </div>
  );
}

function RetryButton({ onClick }: { onClick: () => void }): JSX.Element {
  return (
    <button type="button" onClick={onClick} className="inline-flex w-fit items-center gap-1 rounded border border-outline-variant bg-surface-container-lowest px-2 py-1 text-body-xs font-medium hover:bg-surface-container">
      <RefreshCw aria-hidden className="h-3 w-3" />Retry
    </button>
  );
}
