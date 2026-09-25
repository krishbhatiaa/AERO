import { ArrowLeft } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { AsyncBoundary } from "@/components/AsyncBoundary";
import { BarChart } from "@/components/charts/BarChart";
import { LineChart } from "@/components/charts/LineChart";
import { DataKindBadge } from "@/components/DataKindBadge";
import { KV, Panel } from "@/components/Panel";
import { SeverityChip } from "@/components/SeverityChip";
import { TimeStamp } from "@/components/TimeStamp";
import { StaticMap } from "@/features/map/StaticMap";
import { ProvenancePanel } from "@/features/panels/Panels";
import { useGeoJson } from "@/hooks/useGeoJson";
import { useDownscaled, useEvent, useExplain, useField, useImpact, useTrajectory, useUncertainty } from "@/hooks/queries";
import { leadLabel } from "@/lib/time";
import { fmt, fmtInt, pct } from "@/lib/utils";

const C = { p: "rgb(var(--c-primary))", t: "rgb(var(--c-tertiary))", s: "rgb(var(--c-secondary))", e: "rgb(var(--sev-severe))" };

export function EventDetail(): JSX.Element {
  const { id = "" } = useParams();
  const ev = useEvent(id);
  const traj = useTrajectory(id);
  const unc = useUncertainty(id);
  const ds = useDownscaled(id);
  const lead = ev.data?.peak_lead_hours;
  const explain = useExplain(id, lead);
  const impact = useImpact(id, lead);
  const coarse = useField({ product: "forecast", variable: "tp", lead });
  const fine = useField({ product: "downscaled", variable: "tp", method: "bicubic_conservative", lead });
  const truth = useField({ product: "truth", variable: "tp", lead });
  const countries = useGeoJson("countries_domain.geojson");
  const states = useGeoJson<{ name: string }>("india_states_domain.geojson");
  const bounds: [number, number, number, number] = coarse.data?.payload.bounds ?? [80, 12, 92, 24];
  const trackBounds = ((): [number, number, number, number] => {
    const xy = (traj.data?.features ?? []).filter((f) => f.geometry.type === "Point").map((f) => (f.geometry as { coordinates: [number, number] }).coordinates);
    if (!xy.length) return bounds;
    const xs = xy.map((c) => c[0]), ys = xy.map((c) => c[1]);
    const cx = (Math.min(...xs) + Math.max(...xs)) / 2, cy = (Math.min(...ys) + Math.max(...ys)) / 2;
    const half = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys), 6) / 2 + 1.5;
    return [cx - half * 1.2, cy - half, cx + half * 1.2, cy + half];
  })();
  const pts = traj.data?.features.filter((f) => f.properties.kind === "tracked_point").map((f) => f.properties) ?? [];
  const pctl = explain.data?.factors.find((f) => f.name === "Historical percentile")?.value;

  return (
    <div className="mx-auto max-w-6xl space-y-3 p-4">
      <Link to="/events" className="inline-flex items-center gap-1 text-body-sm font-medium text-primary hover:underline"><ArrowLeft aria-hidden className="h-3.5 w-3.5" />All events</Link>
      <AsyncBoundary query={ev} label="event">
        {(e) => (
          <>
            <header className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <h1 className="text-head-lg">Extreme rainfall event <span className="font-mono text-body-md text-on-surface-variant">{e.id.slice(0, 8)}</span></h1>
                <p className="text-body-sm text-on-surface-variant">{e.attributes.cyclone_like_signature ? "Cyclone-like signature on the coarse control forecast (descriptive, not an operational classification)." : "No cyclone-like signature."}</p>
              </div>
              <div className="flex items-center gap-2"><SeverityChip severity={e.severity} /><DataKindBadge kind={e.data_kind} /></div>
            </header>
            <section aria-label="Key figures" className="grid grid-cols-2 gap-2 md:grid-cols-4">
              {[
                ["Event type", e.event_type.replace("_", " ")], ["Peak intensity", `${fmt(e.peak_intensity.value, 0)} ${e.peak_intensity.unit}`],
                ["Location at peak", `${fmt(e.centroid.lat, 2)}°N, ${fmt(e.centroid.lon, 2)}°E`], ["Forecast horizon", `${leadLabel(0)} – ${leadLabel(e.n_steps * 6 - 6)}`],
                ["Confidence", e.confidence], ["Ensemble agreement", pct(e.probability)], ["Affected area (max)", `${fmtInt(e.max_area_km2)} km²`], ["Historical percentile", typeof pctl === "number" ? `${fmt(pctl, 2)} %` : "—"],
                ["Source", e.provenance.data_source], ["Model", "classical baselines"], ["Uncertainty (p90 @ peak)", unc.data ? `${fmt(unc.data.steps.find((s) => s.lead_hours === lead)?.ensemble_radius_km_p90, 0)} km` : "…"], ["Peak valid time", <TimeStamp key="t" iso={e.peak_valid_time} />],
              ].map(([k, v]) => <div key={String(k)} className="rounded border border-outline-variant/60 bg-surface-container-lowest p-2"><div className="text-label-header uppercase text-on-surface-variant">{k}</div><div className="font-mono text-label-num-lg">{v}</div></div>)}
            </section>
          </>
        )}
      </AsyncBoundary>

      <div className="grid gap-3 lg:grid-cols-2">
        <AsyncBoundary query={traj} label="trajectory charts">
          {() => (
            <>
              <LineChart title="Intensity vs time" description="Peak 6-hour accumulation inside the tracked footprint (control forecast)." unit="mm/6h" xLabel="lead time (h)" xFormat={(x) => `+${x}`} yDigits={0}
                series={[{ name: "peak precipitation", color: C.p, points: pts.map((p) => ({ x: p.lead_hours ?? 0, y: p.max_intensity ?? null })) }]} highlightX={lead} />
              <LineChart title="Area vs time" description="cos(lat)-correct area of the anomaly footprint (≥ P95 of the synthetic climatology)." unit="km²" xLabel="lead time (h)" xFormat={(x) => `+${x}`} yDigits={0}
                series={[{ name: "footprint area", color: C.t, points: pts.map((p) => ({ x: p.lead_hours ?? 0, y: p.area_km2 ?? null })), marker: "square" }]} highlightX={lead} />
            </>
          )}
        </AsyncBoundary>
        <div className="space-y-3">
          <Panel title="Trajectory (synthetic)"><StaticMap bounds={trackBounds} lead={lead ?? 0} trajectory={traj.data} countries={countries.data} states={states.data} ariaLabel="Event trajectory map with uncertainty envelope" className="h-56" />
            <p className="mt-1 text-body-xs text-on-surface-variant">Solid: tracked centroid. Dashed red: extrapolation beyond the last frame. Shaded: ensemble uncertainty envelope (not an NHC cone).</p></Panel>
          <AsyncBoundary query={unc} label="forecast spread">
            {(u) => (
              <LineChart title="Forecast spread" description="Ensemble position spread (p90 radius) and member agreement." unit="km" xLabel="lead time (h)" xFormat={(x) => `+${x}`} yDigits={0}
                series={[{ name: "p90 radius", color: C.s, points: u.steps.map((s) => ({ x: s.lead_hours, y: s.ensemble_radius_km_p90 })) }, { name: "RMS spread", color: C.e, dashed: true, marker: "square", points: u.steps.map((s) => ({ x: s.lead_hours, y: s.ensemble_rms_spread_km })) }]} highlightX={lead} />
            )}
          </AsyncBoundary>
        </div>
        <LineChart title="Minimum sea-level pressure" description="Lowest MSLP of the coarse control forecast (deepens, then fills after landfall)." unit="hPa" xLabel="lead time (h)" xFormat={(x) => `+${x}`} yDigits={0}
          series={[{ name: "min MSLP", color: C.p, points: pts.map((p) => ({ x: p.lead_hours ?? 0, y: p.min_msl_hpa ?? null })) }]} highlightX={lead} />
        <LineChart title="Maximum 10 m wind" description="Strongest 10 m wind speed of the coarse control forecast." unit="m/s" xLabel="lead time (h)" xFormat={(x) => `+${x}`} yDigits={0}
          series={[{ name: "max wind", color: C.e, dashed: true, marker: "square", points: pts.map((p) => ({ x: p.lead_hours ?? 0, y: p.max_wind_ms ?? null })) }]} highlightX={lead} />
      </div>

      <Panel title={`12 km-class → 5 km-class impact view at ${lead !== undefined ? leadLabel(lead) : "…"}`} right={<DataKindBadge kind="SYNTHETIC_DEMO" compact />}>
        <div role="note" className="mb-2 rounded border border-sev-moderate/50 bg-sev-moderate/10 px-2 py-1 text-body-xs">No learned downscaler exists yet: the right panel is a <b>baseline interpolation</b> (bicubic + conservation) of the coarse field, compared with the synthetic fine-grid truth. Nothing here is an AI-derived product.</div>
        <div className="grid gap-2 md:grid-cols-3">
          {([["Coarse forecast", coarse.data], ["Baseline (bicubic + conservation)", fine.data], ["Synthetic fine truth", truth.data]] as const).map(([label, f]) => (
            <figure key={label}><StaticMap bounds={impact.data ? [82, 18, 90, 24] : bounds} lead={lead ?? 0} field={f} impact={impact.data} countries={countries.data} states={states.data} ariaLabel={`${label} precipitation at the peak lead time`} className="h-56" />
              <figcaption className="mt-1 flex justify-between font-mono text-label-num-md"><span className="font-semibold">{label}</span><span>peak {f ? `${fmt(f.payload.max, 0)} mm/6h` : "…"}</span></figcaption></figure>
          ))}
        </div>
        <AsyncBoundary query={ds} label="downscaling metrics" className="mt-3">
          {(d) => (
            <div className="grid gap-3 md:grid-cols-2">
              <BarChart title="Peak preservation" description="Peak error vs synthetic truth (0 = perfect; negative = extreme smoothed)." unit="mm/6h" digits={1}
                bars={d.methods.map((m) => ({ label: m.method, value: m.metrics.peak_error?.mean ?? 0, ci: m.metrics.peak_error ? [m.metrics.peak_error.ci_low, m.metrics.peak_error.ci_high] : undefined, emphasis: m.method === d.default_method }))} />
              <BarChart title="P99 error / spatial detail" description="Error of the 99th percentile (mm/6h). Fine-scale variance recovered is in the table view of the Evaluation page." unit="mm/6h" digits={2}
                bars={d.methods.map((m) => ({ label: m.method, value: m.metrics.p99_error?.mean ?? 0, ci: m.metrics.p99_error ? [m.metrics.p99_error.ci_low, m.metrics.p99_error.ci_high] : undefined, emphasis: m.method === d.default_method }))} />
            </div>
          )}
        </AsyncBoundary>
        <AsyncBoundary query={impact} label="impact geometry" className="mt-3">
          {(i) => (
            <dl className="grid gap-x-6 md:grid-cols-2">
              <KV k="Position uncertainty (p90 radius)" v={`${fmt(i.uncertainty_radius_km, 0)} km`} />
              <KV k="Regions intersecting risk polygon" v={i.regions.risk.map((r) => `${r.name} (${fmt(r.fraction_of_polygon * 100, 0)}%)`).join(", ") || "none"} mono={false} />
            </dl>
          )}
        </AsyncBoundary>
      </Panel>
      <ProvenancePanel event={ev.data} />
    </div>
  );
}
