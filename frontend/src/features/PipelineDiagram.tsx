import { ArrowDown, ArrowRight } from "lucide-react";

import { StatusChip } from "@/components/StatusChip";
import type { CapabilitiesData, CapabilityStatus } from "@/types/api";

interface Stage {
  title: string;
  input: string;
  runs: string;
  caps: string[];
  planned?: string;
  plannedCap?: string;
}

export const STAGES: Stage[] = [
  { title: "INPUT", input: "12 km-class weather fields", runs: "Source adapters (ERA5, IMDAA, IMD, NEPS-G, NCUM, synthetic) → validation → Zarr", caps: ["ingestion"], planned: "Live NEPS-G / IMDAA data", plannedCap: "restricted_sources" },
  { title: "ANOMALY", input: "field + climatology", runs: "Percentile, z-score and EFI-style detectors; region extraction", caps: ["climatology", "anomaly_detectors", "extraction"], planned: "Learned anomaly detector", plannedCap: "ml_anomaly" },
  { title: "GNN", input: "graph on the sphere", runs: "Graph builders: kNN, radius, grid mesh, icosahedral mesh", caps: ["gnn_graphs"], planned: "Spatio-temporal GNN tracker", plannedCap: "gnn_tracking" },
  { title: "TRACK", input: "regions through time", runs: "Gated Hungarian association + constant-velocity Kalman filter", caps: ["tracking_baseline"] },
  { title: "DIFFUSION / DOWNSCALE", input: "coarse field + terrain", runs: "Interpolation baselines with conservation (nearest → bicubic)", caps: ["downscaling_baselines"], planned: "CNN / U-Net, conditional diffusion", plannedCap: "diffusion" },
  { title: "5 KM FIELD", input: "fine-grid product", runs: "Baseline 5 km-class field, always labelled with its method", caps: ["downscaling_baselines"] },
  { title: "PHYSICS", input: "fine + coarse fields", runs: "Conservation, non-negativity, saturation, divergence diagnostics", caps: ["physics_checks"], planned: "Physics-informed training loss", plannedCap: "physics_loss" },
  { title: "RISK", input: "event descriptors", runs: "Configurable risk engine → impact polygons → alerts", caps: ["risk", "impact", "alerts"] },
];

const RANK: Record<CapabilityStatus, number> = { IMPLEMENTED: 0, PARTIALLY_IMPLEMENTED: 1, REQUIRES_REAL_DATA: 2, REQUIRES_GPU_TRAINING: 3, RESEARCH_EXTENSION: 4 };

function worst(caps: CapabilitiesData | undefined, ids: string[]): CapabilityStatus | "PENDING" {
  if (!caps) return "PENDING";
  const found = ids.map((i) => caps.capabilities.find((c) => c.id === i)?.status).filter((s): s is CapabilityStatus => !!s);
  return found.length ? found.reduce((a, b) => (RANK[a] >= RANK[b] ? a : b)) : "PENDING";
}

/** Input → anomaly → GNN → track → downscale → 5 km → physics → risk, with the true implementation status of each stage. */
export function PipelineDiagram({ caps }: { caps: CapabilitiesData | undefined }): JSX.Element {
  return (
    <ol className="grid gap-2 md:grid-cols-4 xl:grid-cols-8" aria-label="Processing pipeline">
      {STAGES.map((s, i) => (
        <li key={s.title} className="relative flex flex-col gap-1.5 rounded border border-outline-variant/70 bg-surface-container-lowest p-2.5">
          <div className="flex items-center justify-between"><span className="font-mono text-label-num-sm text-on-surface-variant">{String(i + 1).padStart(2, "0")}</span>
            {i < STAGES.length - 1 && <><ArrowRight aria-hidden className="hidden h-3.5 w-3.5 text-outline xl:block" /><ArrowDown aria-hidden className="h-3.5 w-3.5 text-outline xl:hidden" /></>}</div>
          <div className="text-label-header uppercase text-primary">{s.title}</div>
          <div className="text-body-xs text-on-surface-variant">{s.input}</div>
          <div className="text-[10px] font-semibold uppercase text-on-surface-variant">Runs now</div>
          <div className="text-body-xs">{s.runs}</div>
          <StatusChip status={worst(caps, s.caps)} className="self-start" />
          {s.planned && s.plannedCap && (
            <div className="mt-auto border-t border-dashed border-outline-variant pt-1.5">
              <div className="text-[10px] font-semibold uppercase text-on-surface-variant">Planned</div>
              <div className="mb-1 text-body-xs">{s.planned}</div>
              <StatusChip status={worst(caps, [s.plannedCap])} />
            </div>
          )}
        </li>
      ))}
    </ol>
  );
}
