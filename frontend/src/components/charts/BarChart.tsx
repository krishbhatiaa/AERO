import { ChartFrame } from "./ChartFrame";
import { niceTicks } from "./LineChart";

export interface Bar {
  label: string;
  value: number;
  ci?: [number, number];
  emphasis?: boolean;
}
interface Props {
  title: string;
  description: string;
  unit: string;
  bars: Bar[];
  digits?: number;
  reference?: { value: number; label: string };
}

const W = 340;
const ROW = 26;
const M = { l: 132, r: 52, t: 6, b: 22 }; // right margin = dedicated value column (no label/whisker collisions)

/** Horizontal bar chart with optional 95 % CI whiskers, a zero line and an optional reference line. */
export function BarChart({ title, description, unit, bars, digits = 1, reference }: Props): JSX.Element {
  const vals = bars.flatMap((b) => [b.value, ...(b.ci ?? [])]).concat(reference ? [reference.value] : []).concat([0]);
  const ticks = niceTicks(Math.min(...vals), Math.max(...vals), 4);
  const lo = ticks[0] ?? 0, hi = ticks[ticks.length - 1] ?? 1;
  const H = M.t + bars.length * ROW + M.b;
  const X = (v: number): number => M.l + ((v - lo) / Math.max(hi - lo, 1e-9)) * (W - M.l - M.r);
  const chart = (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${title}. ${description}. Use the table view for exact values.`} className="w-full">
      {ticks.map((t) => (
        <g key={t}>
          <line x1={X(t)} x2={X(t)} y1={M.t} y2={H - M.b} stroke="rgb(var(--c-outline-variant))" strokeOpacity={0.45} strokeWidth={0.6} />
          <text x={X(t)} y={H - 8} textAnchor="middle" fontSize={9} className="fill-on-surface-variant font-mono">{t.toFixed(digits)}</text>
        </g>
      ))}
      <line x1={X(0)} x2={X(0)} y1={M.t} y2={H - M.b} stroke="rgb(var(--c-on-surface))" strokeWidth={1} />
      {reference && <line x1={X(reference.value)} x2={X(reference.value)} y1={M.t} y2={H - M.b} stroke="rgb(var(--sev-moderate))" strokeWidth={1.2} strokeDasharray="4 3"><title>{reference.label}</title></line>}
      {bars.map((b, i) => {
        const y = M.t + i * ROW + 5;
        const x0 = X(Math.min(0, b.value)), w = Math.abs(X(b.value) - X(0));
        return (
          <g key={b.label}>
            <text x={M.l - 6} y={y + 9} textAnchor="end" fontSize={10} className="fill-on-surface font-mono">{b.label}</text>
            <rect x={x0} y={y} width={Math.max(w, 1)} height={14} rx={2} fill={b.emphasis ? "rgb(var(--c-primary))" : "rgb(var(--c-outline))"} fillOpacity={b.emphasis ? 0.95 : 0.65} />
            {b.ci && <g stroke="rgb(var(--c-on-surface))" strokeWidth={1}><line x1={X(b.ci[0])} x2={X(b.ci[1])} y1={y + 7} y2={y + 7} /><line x1={X(b.ci[0])} x2={X(b.ci[0])} y1={y + 3} y2={y + 11} /><line x1={X(b.ci[1])} x2={X(b.ci[1])} y1={y + 3} y2={y + 11} /></g>}
            <text x={W - 4} y={y + 10.5} textAnchor="end" fontSize={10} fontWeight={600} className="fill-on-surface font-mono">{b.value.toFixed(digits)}</text>
          </g>
        );
      })}
      <text x={W - 4} y={H - 8} textAnchor="end" fontSize={9} className="fill-on-surface-variant">{unit}</text>
    </svg>
  );
  const rows = bars.map((b) => [b.label, b.value.toFixed(digits), b.ci ? `${b.ci[0].toFixed(digits)} to ${b.ci[1].toFixed(digits)}` : "—"]);
  return <ChartFrame title={title} description={description} chart={chart} table={{ headers: ["Method", `Value (${unit})`, "95% CI (bootstrap over frames)"], rows }} />;
}
