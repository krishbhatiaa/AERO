import { ANOMALY_STOPS, PRECIP_STOPS, type RGBA, type Stop } from "@/lib/colors";

function luminance(r: number, g: number, b: number): number {
  const lin = (v: number): number => { const c = v / 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}
const DARK = "#0f172a";
const DARK_L = luminance(15, 23, 42);

/** Black-ish or white label text, whichever has the higher WCAG contrast against the swatch colour. */
export function labelTextColor([r, g, b]: RGBA): string {
  const L = luminance(r, g, b);
  return 1.05 / (L + 0.05) >= (L + 0.05) / (DARK_L + 0.05) ? "#ffffff" : DARK;
}
export function labelContrast(c: RGBA): number {
  const L = luminance(c[0], c[1], c[2]);
  return labelTextColor(c) === "#ffffff" ? 1.05 / (L + 0.05) : (L + 0.05) / (DARK_L + 0.05);
}

function Bar({ stops, title, unit }: { stops: Stop[]; title: string; unit: string }): JSX.Element {
  return (
    <div>
      <div className="mb-0.5 text-label-header uppercase text-on-surface-variant">{title} <span className="font-mono font-normal normal-case">({unit})</span></div>
      <div className="flex shadow-sm" role="img" aria-label={`${title} colour scale: ${stops.map((s) => s.label).join(", ")} ${unit}`}>
        {stops.map((s) => (
          <div key={s.label} className="flex h-4 min-w-[26px] items-center justify-center px-1 font-mono text-[9px] font-bold" style={{ background: `rgb(${s.color[0]} ${s.color[1]} ${s.color[2]})`, color: labelTextColor(s.color) }}>{s.label}</div>
        ))}
      </div>
    </div>
  );
}

export function Legend({ showAnomaly }: { showAnomaly: boolean }): JSX.Element {
  return (
    <div className="glass flex flex-col gap-1.5 rounded border border-outline-variant/60 p-2 shadow">
      <Bar stops={PRECIP_STOPS} title="Precipitation" unit="mm per 6 h, values below 1 transparent" />
      {showAnomaly && <Bar stops={ANOMALY_STOPS} title="Anomaly score" unit="climatological percentile rank" />}
    </div>
  );
}
