import { useState } from "react";
import { AlertTriangle, Download, Eye, MapPin } from "lucide-react";

import { AsyncBoundary } from "@/components/AsyncBoundary";
import { ControlButton } from "@/components/ControlButton";
import { DataKindBadge } from "@/components/DataKindBadge";
import { Dialog } from "@/components/Dialog";
import { KV } from "@/components/Panel";
import { SeverityChip } from "@/components/SeverityChip";
import { TimeStamp } from "@/components/TimeStamp";
import { useAlerts } from "@/hooks/queries";
import { downloadResource } from "@/lib/api";
import { fmt, fmtInt, pct } from "@/lib/utils";
import type { Alert } from "@/types/api";

function AlertDetail({ a }: { a: Alert }): JSX.Element {
  const [busy, setBusy] = useState(false);
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3"><SeverityChip severity={a.severity} /><DataKindBadge kind={a.data_kind} /></div>
      <dl className="grid grid-cols-2 gap-3 rounded-xl bg-surface-container-low p-4">
        <KV k="Event" v={`${a.event_type.replace("_", " ")} · ${a.event_id.slice(0, 8)}`} />
        <KV k="Location" v={a.location.summary} mono={false} />
        <KV k="Centroid at peak" v={`${fmt(a.location.centroid.lat, 2)}°N, ${fmt(a.location.centroid.lon, 2)}°E (T+${a.location.peak_lead_hours})`} />
        <KV k="Forecast period (from)" v={<TimeStamp iso={a.forecast_window.start} />} />
        <KV k="Forecast period (to)" v={<TimeStamp iso={a.forecast_window.end} />} />
        <KV k="Probability (ensemble agreement)" v={pct(a.probability)} />
        <KV k="Confidence" v={a.confidence} />
        <KV k="Position uncertainty (p90)" v={`${fmt(a.uncertainty.position_radius_km_p90, 0)} km`} />
        <KV k="Max footprint area" v={`${fmtInt(a.affected_area.km2_footprint_max)} km²`} />
        <KV k="Source" v={a.source} mono={false} />
        <KV k="Model version" v={a.model_version} mono={false} />
      </dl>
      <div>
        <h3 className="mb-2 text-xs font-semibold text-on-surface uppercase tracking-wide">Affected Administrative Regions (Risk Polygon)</h3>
        <div className="overflow-hidden rounded-xl border border-outline-variant/40">
          <table className="w-full border-collapse text-left font-mono text-xs">
            <thead><tr className="bg-surface-container-low">
              <th scope="col" className="px-3 py-2 font-medium text-on-surface-variant">Region</th>
              <th scope="col" className="px-3 py-2 text-right font-medium text-on-surface-variant">Overlap km²</th>
              <th scope="col" className="px-3 py-2 text-right font-medium text-on-surface-variant">% of polygon</th>
              <th scope="col" className="px-3 py-2 text-right font-medium text-on-surface-variant">% of region</th>
            </tr></thead>
            <tbody>{a.affected_area.regions_risk_polygon.map((r) => (
              <tr key={r.region_id} className="border-t border-outline-variant/20 hover:bg-surface-container">
                <th scope="row" className="px-3 py-2 font-medium">{r.name}</th>
                <td className="px-3 py-2 text-right">{fmtInt(r.intersect_area_km2)}</td>
                <td className="px-3 py-2 text-right">{fmt(r.fraction_of_polygon * 100, 1)}%</td>
                <td className="px-3 py-2 text-right">{fmt(r.fraction_of_region * 100, 1)}%</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
        <p className="mt-1 text-[10px] text-on-surface-variant">Boundaries: {a.affected_area.boundary_source}</p>
      </div>
      <div>
        <h3 className="mb-2 text-xs font-semibold text-on-surface uppercase tracking-wide">Risk Rationale</h3>
        <ul className="space-y-1 rounded-xl bg-surface-container-low p-3 text-sm">{a.risk.rationale.map((r) => <li key={r} className="flex items-start gap-2"><span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />{r}</li>)}</ul>
      </div>
      <div role="note" className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-3 text-sm">
        <b className="text-amber-400">Verification: </b>{a.verification}<br />
        <span className="text-on-surface-variant text-xs">{a.disclaimer}</span>
      </div>
      <ControlButton label="Export alert as GeoJSON" icon={Download} loading={busy} variant="solid" onClick={() => { setBusy(true); void downloadResource(`/alerts/${a.id}/geojson`, `alert-${a.id.slice(0, 8)}.geojson`).finally(() => setBusy(false)); }}>Export GeoJSON</ControlButton>
    </div>
  );
}

export function Alerts(): JSX.Element {
  const q = useAlerts();
  const [open, setOpen] = useState<Alert | null>(null);
  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      {/* Header */}
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-on-surface flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-500/10">
              <AlertTriangle className="h-5 w-5 text-amber-400" />
            </div>
            Alerts
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-on-surface-variant">
            Analytical decision-support alerts derived from tracked events. They are <b>not official warnings</b> and contain no emergency instructions.
          </p>
        </div>
      </div>

      {/* Alerts List */}
      <AsyncBoundary query={q} label="alerts" isEmpty={(d) => d.length === 0} emptyText="No alerts have been generated.">
        {(alerts) => (
          <div className="space-y-3">
            {alerts.map((a) => {
              const sevColor = a.severity === "SEVERE" ? "border-red-500/30 hover:border-red-500/50" : a.severity === "MODERATE" ? "border-amber-500/30 hover:border-amber-500/50" : "border-outline-variant/40 hover:border-primary/30";
              return (
                <div key={a.id} className={`rounded-xl border bg-surface-container-lowest p-4 transition-all ${sevColor}`}>
                  <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                    <div className="flex items-center gap-4">
                      <SeverityChip severity={a.severity} />
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-semibold text-on-surface">{a.location.summary}</span>
                        </div>
                        <div className="mt-1 flex items-center gap-3 text-xs text-on-surface-variant">
                          <span className="flex items-center gap-1"><MapPin className="h-3 w-3" />{fmt(a.location.centroid.lat, 1)}°N, {fmt(a.location.centroid.lon, 1)}°E</span>
                          <span>·</span>
                          <TimeStamp iso={a.forecast_window.start} compact /> → <TimeStamp iso={a.forecast_window.end} compact />
                          <span>·</span>
                          <span>{pct(a.probability)} probability</span>
                          <span>·</span>
                          <span>{a.confidence} confidence</span>
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <DataKindBadge kind={a.data_kind} compact />
                      <button onClick={() => setOpen(a)} className="flex items-center gap-1.5 rounded-lg border border-outline-variant/40 bg-surface-container px-3 py-1.5 text-xs font-medium text-on-surface transition hover:border-primary/40 hover:bg-primary/10 hover:text-primary">
                        <Eye className="h-3 w-3" />
                        Details
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </AsyncBoundary>

      {open && <Dialog open onOpenChange={(o) => { if (!o) setOpen(null); }} title="Alert Details" description="Analytical decision support. Not an official warning."><AlertDetail a={open} /></Dialog>}
    </div>
  );
}
