import { AsyncBoundary } from "@/components/AsyncBoundary";
import { BarChart } from "@/components/charts/BarChart";
import { LineChart } from "@/components/charts/LineChart";
import { DataKindBadge } from "@/components/DataKindBadge";
import { Panel } from "@/components/Panel";
import { useDownscalingEval, useTrackingEval } from "@/hooks/queries";
import { fmt } from "@/lib/utils";
import type { DownscalingEval } from "@/types/api";

const bars = (d: DownscalingEval, key: string) => d.methods.map((m) => {
  const s = m.metrics[key];
  return { label: m.method, value: s?.mean ?? 0, ci: s ? ([s.ci_low, s.ci_high] as [number, number]) : undefined, emphasis: m.method === "bicubic_conservative" };
});

export function Analytics(): JSX.Element {
  const ds = useDownscalingEval();
  const tr = useTrackingEval();
  return (
    <div className="mx-auto max-w-6xl space-y-4 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2"><div><h1 className="text-head-lg">Evaluation</h1><p className="text-body-sm text-on-surface-variant">Nothing is judged on RMSE alone. All numbers below are computed by the running backend from the synthetic scenario.</p></div><DataKindBadge kind="SYNTHETIC_DEMO" /></div>
      <AsyncBoundary query={ds} label="downscaling evaluation">
        {(d) => (
          <>
            <div role="note" className="rounded border border-sev-moderate/50 bg-sev-moderate/10 p-3 text-body-sm"><b>Read this first: </b>{d.caveat} Learned models evaluated: <b>{(d.learned_models_evaluated || []).length || "none"}</b>.</div>
            <div className="grid gap-3 lg:grid-cols-2">
              <BarChart title="Peak error" description="max(pred) − max(truth). Negative = the extreme peak is smoothed away." unit="mm/6h" bars={bars(d, "peak_error")} />
              <BarChart title="P99 error" description="99th-percentile error vs synthetic truth." unit="mm/6h" digits={2} bars={bars(d, "p99_error")} />
              <BarChart title="Fine-scale variance recovered (PSD ratio)" description="Power at 12–40 km wavelengths relative to truth. 1 = fully recovered. Nearest-neighbour blockiness adds spurious power." unit="ratio" digits={2} bars={bars(d, "psd_ratio_band")} reference={{ value: 1, label: "perfect recovery = 1" }} />
              <BarChart title="RMSE (for context only)" description="Root-mean-square error; hides peak loss." unit="mm/6h" digits={2} bars={bars(d, "rmse")} />
              <BarChart title="Extreme recall" description="Fraction of truth ≥ P99 cells also ≥ P99 in the prediction." unit="fraction" digits={2} bars={bars(d, "extreme_recall")} />
              <BarChart title="Extreme precision" description="Fraction of predicted ≥ P99 cells that are truly ≥ P99." unit="fraction" digits={2} bars={bars(d, "extreme_precision")} />
            </div>
            <Panel title="Full metric table (mean, 95 % bootstrap CI over frames)">
              <div className="overflow-x-auto"><table className="w-full border-collapse text-left font-mono text-label-num-md">
                <caption className="sr-only">All downscaling metrics per method</caption>
                <thead><tr><th scope="col" className="border-b border-outline-variant py-1 pr-2">metric</th>{d.methods.map((m) => <th key={m.method} scope="col" className="border-b border-outline-variant px-2 text-right">{m.method}</th>)}</tr></thead>
                <tbody>{Object.keys(d.methods[0]?.metrics ?? {}).map((k) => <tr key={k} className="odd:bg-surface-container-low"><th scope="row" className="py-0.5 pr-2 text-left font-medium">{k}</th>{d.methods.map((m) => <td key={m.method} className="px-2 text-right">{fmt(m.metrics[k]?.mean, 3)} <span className="text-on-surface-variant">[{fmt(m.metrics[k]?.ci_low, 2)}, {fmt(m.metrics[k]?.ci_high, 2)}]</span></td>)}</tr>)}</tbody>
              </table></div>
            </Panel>
          </>
        )}
      </AsyncBoundary>
      <AsyncBoundary query={tr} label="tracking evaluation">
        {(t) => (
          <div className="grid gap-3 lg:grid-cols-2">
            <LineChart title="Track extrapolation hindcast" description="Error of predicting the next centroid positions: Kalman filter vs persistence (no movement)." unit="km" xLabel="horizon (6 h steps)" yDigits={0}
              series={[{ name: "Kalman", color: "rgb(var(--c-primary))", points: t.hindcast.horizon_steps.map((h) => ({ x: Number(h), y: t.hindcast.kalman_km[h] ?? null })) }, { name: "Persistence", color: "rgb(var(--sev-severe))", dashed: true, marker: "square", points: t.hindcast.horizon_steps.map((h) => ({ x: Number(h), y: t.hindcast.persistence_km[h] ?? null })) }]} />
            <Panel title="Tracking summary"><dl className="font-mono text-label-num-md">{Object.entries(t.summary).filter(([k]) => k !== "note").map(([k, v]) => <div key={k} className="flex justify-between py-0.5"><dt className="text-on-surface-variant">{k}</dt><dd>{typeof v === "number" ? fmt(v, 2) : String(v)}</dd></div>)}</dl><p className="mt-2 text-body-xs text-on-surface-variant">{t.caveat}</p></Panel>
          </div>
        )}
      </AsyncBoundary>
    </div>
  );
}
