import { ChartFrame } from "./ChartFrame";

export interface Point {
  x: number;
  y: number | null;
}
export interface Series {
  name: string;
  points: Point[];
  color: string;
  dashed?: boolean;
  marker?: "circle" | "square";
}
interface Props {
  title: string;
  description: string;
  unit: string;
  xLabel: string;
  series: Series[];
  highlightX?: number;
  height?: number;
  xFormat?: (x: number) => string;
  yDigits?: number;
}

export function niceTicks(lo: number, hi: number, n = 4): number[] {
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return [0, 1];
  if (hi === lo) return [lo - 1, lo, lo + 1];
  const raw = (hi - lo) / n;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = ([1, 2, 2.5, 5, 10].find((m) => m * mag >= raw) ?? 10) * mag;
  const out: number[] = [];
  const first = Math.floor(lo / step + 1e-9) * step;
  const last = Math.ceil(hi / step - 1e-9) * step; // always include a tick at or above the data maximum
  for (let v = first; v <= last + step * 1e-6; v += step) out.push(Number(v.toFixed(10)));
  return out;
}

const W = 340;
const M = { l: 44, r: 10, t: 16, b: 30 };

/** Small dependency-free SVG line chart. Series differ by dash pattern and marker shape, not colour alone. */
export function LineChart({ title, description, unit, xLabel, series, highlightX, height = 170, xFormat = String, yDigits = 1 }: Props): JSX.Element {
  const xs = series.flatMap((s) => s.points.map((p) => p.x));
  const ys = series.flatMap((s) => s.points.map((p) => p.y).filter((y): y is number => y !== null && Number.isFinite(y)));
  const xmin = Math.min(...xs), xmax = Math.max(...xs);
  const yt = niceTicks(Math.min(...ys), Math.max(...ys));
  const ymin = yt[0] ?? 0, ymax = yt[yt.length - 1] ?? 1;
  const X = (x: number): number => M.l + ((x - xmin) / Math.max(xmax - xmin, 1e-9)) * (W - M.l - M.r);
  const Y = (y: number): number => height - M.b - ((y - ymin) / Math.max(ymax - ymin, 1e-9)) * (height - M.t - M.b);
  const xTicks = [...new Set(xs)].sort((a, b) => a - b);
  const step = Math.ceil(xTicks.length / 6);
  const chart = (
    <svg viewBox={`0 0 ${W} ${height}`} role="img" aria-label={`${title}. ${description}. Use the table view for exact values.`} className="w-full">
      {yt.map((t) => (
        <g key={t}>
          <line x1={M.l} x2={W - M.r} y1={Y(t)} y2={Y(t)} stroke="rgb(var(--c-outline-variant))" strokeOpacity={0.5} strokeWidth={0.6} />
          <text x={M.l - 5} y={Y(t) + 3} textAnchor="end" fontSize={9} className="fill-on-surface-variant font-mono">{t.toFixed(yDigits)}</text>
        </g>
      ))}
      {xTicks.map((t, i) => (i % step === 0 ? <text key={t} x={X(t)} y={height - M.b + 12} textAnchor="middle" fontSize={9} className="fill-on-surface-variant font-mono">{xFormat(t)}</text> : null))}
      <text x={(M.l + W - M.r) / 2} y={height - 3} textAnchor="middle" fontSize={9} className="fill-on-surface-variant">{xLabel}</text>
      <text x={M.l - 40} y={9} fontSize={9} className="fill-on-surface-variant">{unit}</text>
      {highlightX !== undefined && highlightX >= xmin && highlightX <= xmax && (
        <line x1={X(highlightX)} x2={X(highlightX)} y1={M.t} y2={height - M.b} stroke="rgb(var(--c-primary))" strokeWidth={1} strokeDasharray="2 2" />
      )}
      {series.map((s) => {
        const pts = s.points.filter((p): p is { x: number; y: number } => p.y !== null && Number.isFinite(p.y));
        const d = pts.map((p, i) => `${i ? "L" : "M"}${X(p.x).toFixed(1)} ${Y(p.y).toFixed(1)}`).join("");
        return (
          <g key={s.name}>
            <path d={d} fill="none" stroke={s.color} strokeWidth={1.8} strokeDasharray={s.dashed ? "5 3" : undefined} />
            {pts.map((p) => (s.marker === "square"
              ? <rect key={p.x} x={X(p.x) - 2.5} y={Y(p.y) - 2.5} width={5} height={5} fill={s.color} />
              : <circle key={p.x} cx={X(p.x)} cy={Y(p.y)} r={2.6} fill={s.color} />))}
          </g>
        );
      })}
    </svg>
  );
  const legend = (
    <ul className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-body-xs text-on-surface-variant">
      {series.map((s) => (
        <li key={s.name} className="flex items-center gap-1">
          <svg width="18" height="8" aria-hidden><line x1="0" x2="18" y1="4" y2="4" stroke={s.color} strokeWidth="2" strokeDasharray={s.dashed ? "5 3" : undefined} /></svg>
          {s.name}
        </li>
      ))}
    </ul>
  );
  const rows = xTicks.map((x) => [xFormat(x), ...series.map((s) => { const y = s.points.find((p) => p.x === x)?.y; return y === null || y === undefined ? "—" : y.toFixed(yDigits); })]);
  return <ChartFrame title={title} description={description} chart={<>{chart}{legend}</>} table={{ headers: [xLabel, ...series.map((s) => `${s.name} (${unit})`)], rows }} />;
}
