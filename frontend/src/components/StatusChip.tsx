import { CheckCircle2, CircleDashed, Cpu, Database, FlaskConical, Hourglass } from "lucide-react";

import { cn } from "@/lib/utils";
import type { CapabilityStatus } from "@/types/api";

const META: Record<CapabilityStatus, { label: string; Icon: typeof CheckCircle2; cls: string }> = {
  IMPLEMENTED: { label: "IMPLEMENTED", Icon: CheckCircle2, cls: "border-primary/60 text-primary" },
  PARTIALLY_IMPLEMENTED: { label: "PARTIAL", Icon: CircleDashed, cls: "border-sev-moderate/70 text-sev-moderate" },
  REQUIRES_REAL_DATA: { label: "NEEDS REAL DATA", Icon: Database, cls: "border-tertiary/70 text-tertiary" },
  REQUIRES_GPU_TRAINING: { label: "NEEDS GPU TRAINING", Icon: Cpu, cls: "border-secondary/70 text-secondary" },
  RESEARCH_EXTENSION: { label: "RESEARCH", Icon: FlaskConical, cls: "border-outline text-on-surface-variant" },
};

export function statusLabel(s: CapabilityStatus): string {
  return META[s].label;
}

/** Capability status with icon + text (never colour alone). */
export function StatusChip({ status, className }: { status: CapabilityStatus | "PENDING"; className?: string }): JSX.Element {
  if (status === "PENDING") return <span className={cn("inline-flex items-center gap-1 rounded border border-outline px-1.5 py-[1px] font-mono text-label-num-sm", className)}><Hourglass aria-hidden className="h-3 w-3" />PENDING</span>;
  const m = META[status];
  return (
    <span data-status={status} className={cn("inline-flex items-center gap-1 rounded border px-1.5 py-[1px] font-mono text-label-num-sm font-semibold", m.cls, className)}>
      <m.Icon aria-hidden className="h-3 w-3" />{m.label}
    </span>
  );
}
