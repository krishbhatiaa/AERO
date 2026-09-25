import { OctagonAlert, ShieldCheck, TriangleAlert } from "lucide-react";

import { cn } from "@/lib/utils";
import type { Severity } from "@/types/api";

const META: Record<Severity, { Icon: typeof ShieldCheck; cls: string; label: string }> = {
  LOW: { Icon: ShieldCheck, cls: "border-sev-low/60 text-sev-low bg-sev-low/10", label: "LOW" },
  MODERATE: { Icon: TriangleAlert, cls: "border-sev-moderate/70 text-sev-moderate bg-sev-moderate/10", label: "MODERATE" },
  SEVERE: { Icon: OctagonAlert, cls: "border-sev-severe/70 text-sev-severe bg-sev-severe/10", label: "SEVERE" },
};

/** Severity is conveyed by icon + text + border weight, never by colour alone. Not an official warning category. */
export function SeverityChip({ severity, className }: { severity: Severity; className?: string }): JSX.Element {
  const m = META[severity];
  return (
    <span
      data-testid="severity-chip"
      role="img"
      aria-label={`Analytical severity ${m.label}. Not an official warning category.`}
      className={cn("inline-flex items-center gap-1 rounded border px-1.5 py-[1px] font-mono text-label-num-md font-bold", severity === "SEVERE" ? "border-2" : "", m.cls, className)}
    >
      <m.Icon aria-hidden className="h-3.5 w-3.5" />
      {m.label}
    </span>
  );
}
