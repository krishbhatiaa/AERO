import { Bell, Download, GitBranch, Layers, ListChecks, MapPinned, ShieldQuestion, Waves } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { AsyncBoundary } from "@/components/AsyncBoundary";
import { ControlButton } from "@/components/ControlButton";
import { DataKindBadge } from "@/components/DataKindBadge";
import { KV, Panel } from "@/components/Panel";
import { SeverityChip } from "@/components/SeverityChip";
import { TimeStamp } from "@/components/TimeStamp";
import { useAlerts, useDownscaled, useExplain, useTrajectory, useUncertainty } from "@/hooks/queries";
import { downloadResource } from "@/lib/api";
import { bearingToCompass, fmt, fmtInt, pct } from "@/lib/utils";
import { leadLabel } from "@/lib/time";
import { useUi } from "@/stores/ui";
import type { EventSummary } from "@/types/api";

import { useSelectedEvent } from "./useSelected";

export function EventPanel({ lead }: { lead: number | undefined }): JSX.Element {
  const { event, events } = useSelectedEvent();
  const select = useUi((s) => s.selectEvent);
  const traj = useTrajectory(event?.id ?? null);
  const pt = traj.data?.features.find((f) => f.properties.kind === "tracked_point" && f.properties.lead_hours === lead)?.properties;
  return (
    <Panel title="Event monitor" icon={Waves} right={event && <SeverityChip severity={event.severity} />}>
      {!event ? <div className="text-on-surface-variant">No events detected.</div> : (
        <div className="space-y-2">
          {events.length > 1 && (
            <ul className="flex flex-wrap gap-1" aria-label="Events">
              {events.map((e) => <li key={e.id}><button type="button" aria-pressed={e.id === event.id} onClick={() => select(e.id)} className="rounded border border-outline-variant px-2 py-0.5 font-mono text-label-num-sm aria-pressed:bg-primary aria-pressed:text-on-primary">{e.id.slice(0, 8)}</button></li>)}
            </ul>
          )}
          <div className="flex items-baseline justify-between"><span className="text-head-md">EXTREME RAINFALL · {event.attributes.cyclone_like_signature ? "cyclone-like signature" : "no cyclone signature"}</span></div>
          <div className="flex flex-wrap gap-1.5"><DataKindBadge kind={event.data_kind} /></div>
          <dl className="rounded bg-surface-container-low p-2">
            <KV k="Peak intensity" v={`${fmt(event.peak_intensity.value, 0)} ${event.peak_intensity.unit} (T+${event.peak_lead_hours})`} strong />
            <KV k="Max footprint area" v={`${fmtInt(event.max_area_km2)} km²`} />
            <KV k={`Now (${lead !== undefined ? leadLabel(lead) : "—"}) intensity`} v={pt?.max_intensity !== undefined ? `${fmt(pt.max_intensity, 0)} mm/6h` : "—"} />
            <KV k="Motion" v={pt?.speed_kmh === undefined ? "—" : pt.speed_kmh < 0.5 ? "no estimate yet (first frame)" : `${fmt(pt.speed_kmh, 0)} km/h toward ${fmt(pt.bearing_deg, 0)}° ${bearingToCompass(pt.bearing_deg ?? 0)}`} />
            <KV k="Min pressure / max wind" v={pt?.min_msl_hpa !== undefined ? `${fmt(pt.min_msl_hpa, 0)} hPa / ${fmt(pt.max_wind_ms, 0)} m/s` : "—"} />
            <KV k="Ensemble agreement" v={pct(event.probability)} />
            <KV k="Confidence class" v={event.confidence} />
            <KV k="Risk score" v={`${fmt(event.risk_score, 2)} (analytical, not official)`} />
          </dl>
          <p className="text-body-xs text-on-surface-variant">{event.disclaimer}</p>
        </div>
      )}
    </Panel>
  );
}

export function ExplainPanel({ eventId, lead }: { eventId: string | null; lead: number | undefined }): JSX.Element {
  const q = useExplain(eventId, lead);
  return (
    <Panel title="Why this event?" icon={ShieldQuestion}>
      <AsyncBoundary query={q} label="explanation" isEmpty={() => !eventId}>
        {(d) => (
          <>
            <dl>{(d.factors || []).map((f) => <KV key={f.name} k={f.name} v={<span title={f.detail}>{typeof f.value === "number" ? fmt(f.value, Math.abs(f.value) < 10 ? 2 : 0) : f.value} <span className="text-on-surface-variant">{f.unit}</span></span>} />)}</dl>
            <ul className="mt-2 list-disc space-y-0.5 pl-4 text-body-xs text-on-surface-variant">{(d.notes || []).map((n) => <li key={n}>{n}</li>)}</ul>
          </>
        )}
      </AsyncBoundary>
    </Panel>
  );
}

export function EnsemblePanel({ eventId, lead }: { eventId: string | null; lead: number | undefined }): JSX.Element {
  const q = useUncertainty(eventId);
  return (
    <Panel title="Ensemble & uncertainty" icon={GitBranch} right={q.data && <span className="font-mono text-label-num-sm text-on-surface-variant">{q.data.n_members} members (synthetic)</span>}>
      <AsyncBoundary query={q} label="uncertainty" isEmpty={(d) => d.steps.length === 0}>
        {(d) => {
          const s = d.steps.find((x) => x.lead_hours === lead);
          const maxR = Math.max(...d.steps.map((x) => x.ensemble_radius_km_p90 ?? 0), 1);
          return (
            <>
              <div className="mb-2 flex items-end gap-[3px]" role="img" aria-label={`Ensemble position spread by lead time: ${d.steps.map((x) => `${leadLabel(x.lead_hours)} ${fmt(x.ensemble_radius_km_p90, 0)} km`).join(", ")}`}>
                {d.steps.map((x) => (
                  <div key={x.lead_hours} className="flex flex-1 flex-col items-center gap-0.5">
                    <div className={x.lead_hours === lead ? "w-full rounded-t bg-primary" : "w-full rounded-t bg-outline/60"} style={{ height: 4 + ((x.ensemble_radius_km_p90 ?? 0) / maxR) * 44 }} />
                    <span className="font-mono text-[8px] text-on-surface-variant">{x.lead_hours}</span>
                  </div>
                ))}
              </div>
              {s ? (
                <dl>
                  <KV k="Position spread (p90 radius)" v={s.ensemble_radius_km_p90 !== null ? `${fmt(s.ensemble_radius_km_p90, 0)} km` : "n/a (<2 members)"} />
                  <KV k="Members detecting event" v={`${s.n_members_detected} / ${d.n_members - 1} (${pct(s.member_agreement)})`} />
                  <KV k="Peak tp p10 / p50 / p90" v={`${s.peak_tp_p10_p50_p90_mm.map((x) => fmt(x, 0)).join(" / ")} mm/6h`} />
                  <KV k="EFI-style max" v={fmt(s.efi_style_max, 2)} />
                  <KV k="Confidence" v={<span className="font-semibold">{s.confidence}</span>} mono={false} />
                </dl>
              ) : <div className="text-on-surface-variant">No event tracked at this lead time.</div>}
              <p className="mt-1 text-body-xs text-on-surface-variant">{d.notes[0]}</p>
            </>
          );
        }}
      </AsyncBoundary>
    </Panel>
  );
}

const METHOD_LABEL: Record<string, string> = { nearest: "Nearest (raw)", bilinear: "Bilinear", bicubic: "Bicubic", bicubic_conservative: "Bicubic + conservation" };

export function DownscalePanel({ eventId }: { eventId: string | null }): JSX.Element {
  const q = useDownscaled(eventId);
  return (
    <Panel title="Downscaling baselines (measured)" icon={Layers}>
      <AsyncBoundary query={q} label="downscaling metrics" isEmpty={() => !eventId}>
        {(d) => (
          <>
            <div role="note" className="mb-2 rounded border border-sev-moderate/50 bg-sev-moderate/10 px-2 py-1 text-body-xs">{d.notice}</div>
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-left font-mono text-label-num-md">
                <caption className="sr-only">Downscaling baseline metrics against synthetic fine-grid truth, mean over forecast frames</caption>
                <thead><tr className="text-on-surface-variant"><th scope="col" className="py-1 pr-2 font-medium">METHOD</th><th scope="col" className="px-1 text-right font-medium">RMSE</th><th scope="col" className="px-1 text-right font-medium">PEAK ERR</th><th scope="col" className="px-1 text-right font-medium">P99 ERR</th><th scope="col" className="px-1 text-right font-medium">PSD</th></tr></thead>
                <tbody>
                  {d.methods.map((m) => (
                    <tr key={m.method} className={m.method === d.default_method ? "bg-primary/10 font-semibold" : "odd:bg-surface-container-low"}>
                      <th scope="row" className="py-0.5 pr-2 text-left font-medium">{METHOD_LABEL[m.method] ?? m.method}</th>
                      <td className="px-1 text-right">{fmt(m.metrics.rmse?.mean, 2)}</td>
                      <td className="px-1 text-right">{fmt(m.metrics.peak_error?.mean, 1)}</td>
                      <td className="px-1 text-right">{fmt(m.metrics.p99_error?.mean, 2)}</td>
                      <td className="px-1 text-right">{fmt(m.metrics.psd_ratio_band?.mean, 2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-1 text-body-xs text-on-surface-variant">mm/6h, mean over {Object.keys(d.physics_checks).length} frames vs synthetic truth. Negative peak/P99 error = smoothed extremes. PSD = fine-scale variance recovered (1 = full). Learned model available: <b>{d.learned_model_available ? "yes" : "no"}</b>.</p>
          </>
        )}
      </AsyncBoundary>
    </Panel>
  );
}

export function PhysicsPanel({ eventId, lead }: { eventId: string | null; lead: number | undefined }): JSX.Element {
  const q = useDownscaled(eventId);
  return (
    <Panel title="Physics checks" icon={ListChecks}>
      <AsyncBoundary query={q} label="physics checks" isEmpty={() => !eventId}>
        {(d) => {
          const p = lead !== undefined ? d.physics_checks[String(lead)] : undefined;
          if (!p) return <div className="text-on-surface-variant">No checks for this lead time.</div>;
          return (
            <>
            <dl>
              <KV k="Precip ≥ 0 (violating cells)" v={`${fmt(p.nonneg_violation_fraction * 100, 2)} %`} />
              <KV k="Coarse-cell conservation (max abs)" v={`${p.conservation_max_abs_mm.toExponential(1)} mm`} />
              <KV k="Conservation (max relative)" v={p.conservation_max_rel.toExponential(1)} />
              <KV k="10 m wind divergence (max |∇·V|)" v={p.wind_divergence_max_abs_s1 !== null ? `${p.wind_divergence_max_abs_s1.toExponential(1)} s⁻¹` : "—"} />
              <KV k="Hard constraints" v={<span className="font-bold">{p.checks_passed ? "✔ PASS" : "✘ FAIL"}</span>} mono={false} />
            </dl>
            <p className="pt-1 text-body-xs text-on-surface-variant">Checks apply to the bicubic + conservation product on synthetic fields. Divergence is descriptive, not a proof of dynamical consistency.</p>
            </>
          );
        }}
      </AsyncBoundary>
    </Panel>
  );
}

export function AlertPanel(): JSX.Element {
  const q = useAlerts();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  return (
    <Panel title="Alert (decision support)" icon={Bell} right={<Link to="/alerts" className="text-label-num-sm font-semibold text-primary underline">All alerts</Link>}>
      <AsyncBoundary query={q} label="alerts" isEmpty={(d) => d.length === 0} emptyText="No alerts generated.">
        {(alerts) => {
          const a = alerts[0]!;
          return (
            <div className="space-y-2">
              <div className="flex items-center justify-between"><SeverityChip severity={a.severity} /><DataKindBadge kind={a.data_kind} compact /></div>
              <dl className="rounded bg-surface-container-low p-2">
                <KV k="Regions (risk polygon)" v={a.location.summary} mono={false} />
                <KV k="Window" v={<TimeStamp iso={a.forecast_window.start} compact />} />
                <KV k="Until" v={<TimeStamp iso={a.forecast_window.end} compact />} />
                <KV k="Probability / confidence" v={`${pct(a.probability)} / ${a.confidence}`} />
                <KV k="Position uncertainty (p90)" v={`${fmt(a.uncertainty.position_radius_km_p90, 0)} km`} />
              </dl>
              <p className="text-body-xs text-on-surface-variant">{a.verification}</p>
              <ControlButton label="Export alert as GeoJSON" icon={Download} loading={busy} tooltip="Download the alert polygons and properties as GeoJSON" onClick={() => { setBusy(true); setErr(null); downloadResource(`/alerts/${a.id}/geojson`, `alert-${a.id.slice(0, 8)}.geojson`).catch((e: unknown) => setErr(e instanceof Error ? e.message : "Download failed")).finally(() => setBusy(false)); }}>Export GeoJSON</ControlButton>
              {err && <div role="alert" className="text-body-xs text-error">{err}</div>}
            </div>
          );
        }}
      </AsyncBoundary>
    </Panel>
  );
}

export function ProvenancePanel({ event, validTime }: { event: EventSummary | undefined; validTime?: string }): JSX.Element {
  const p = event?.provenance;
  return (
    <Panel title="Data provenance" icon={MapPinned}>
      {!p ? <div className="text-on-surface-variant">No event selected.</div> : (
        <>
        <dl>
          <KV k="Data source" v={p.data_source} />
          <KV k="Data kind" v={<DataKindBadge kind={p.data_kind} compact />} mono={false} />
          <KV k="Dataset / version" v={`${p.dataset_id} · ${p.dataset_version}`} />
          <KV k="Forecast init" v={p.initialization_time ? <TimeStamp iso={p.initialization_time} /> : "—"} />
          <KV k="Valid time" v={validTime ? <TimeStamp iso={validTime} /> : "—"} />
          <KV k="Model version" v={p.model_version} mono={false} />
          <KV k="Checkpoint" v={p.checkpoint_sha256 ?? "none (no trained model)"} />
          <KV k="Preprocess config hash" v={p.preprocess_config_hash} />
          <KV k="Pipeline config hash" v={p.pipeline_config_hash} />
          <KV k="Git commit" v={p.git_sha ?? "not recorded"} />
          <KV k="Created (UTC)" v={p.created_at.slice(0, 19).replace("T", " ") + " UTC"} />
        </dl>
        <ul className="mt-1 list-disc space-y-0.5 pl-4 text-body-xs text-on-surface-variant">{p.notes.map((n) => <li key={n}>{n}</li>)}</ul>
        </>
      )}
    </Panel>
  );
}
