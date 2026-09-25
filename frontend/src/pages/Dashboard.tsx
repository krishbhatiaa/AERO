import { useEffect, useMemo } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowUpRight, Cloud, Wind, Droplets } from "lucide-react";

import { AsyncBoundary } from "@/components/AsyncBoundary";
import { LayerPanel } from "@/features/map/LayerPanel";
import { MapView } from "@/features/map/MapView";
import { AlertPanel, DownscalePanel, EnsemblePanel, EventPanel, ExplainPanel, PhysicsPanel, ProvenancePanel } from "@/features/panels/Panels";
import { useSelectedEvent } from "@/features/panels/useSelected";
import { TimelineBar } from "@/features/timeline/TimelineBar";
import { useLive } from "@/hooks/live";
import { useGeoJson } from "@/hooks/useGeoJson";
import { useField, useForecast, useImpact, useTrajectory, useEvents, useAlerts } from "@/hooks/queries";
import { apiGet } from "@/lib/api";
import { currentLead, useTimeline } from "@/stores/timeline";
import { useUi } from "@/stores/ui";
import type { FieldPayload } from "@/types/api";
import { decodeField } from "@/lib/field";
import { fmt, fmtInt } from "@/lib/utils";

function StatCard({ icon: Icon, label, value, sub, color = "text-primary" }: { icon: React.ElementType; label: string; value: string; sub?: string; color?: string }) {
  return (
    <div className="rounded-xl border border-outline-variant/40 bg-surface-container-lowest p-4 transition hover:border-primary/30">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
          <Icon className={`h-5 w-5 ${color}`} />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-medium text-on-surface-variant uppercase tracking-wide">{label}</p>
          <p className="mt-0.5 text-lg font-bold text-on-surface font-mono">{value}</p>
          {sub && <p className="mt-0.5 text-[10px] text-on-surface-variant">{sub}</p>}
        </div>
      </div>
    </div>
  );
}

function QuickAlertCard({ alert }: { alert: { id: string; severity: string; location: { summary: string }; probability: number; confidence: string } }) {
  const sevColor = alert.severity === "SEVERE" ? "border-red-500/40 bg-red-500/5" : alert.severity === "MODERATE" ? "border-amber-500/40 bg-amber-500/5" : "border-slate-500/40 bg-slate-500/5";
  return (
    <Link to="/alerts" className={`block rounded-lg border p-3 transition hover:opacity-80 ${sevColor}`}>
      <div className="flex items-center justify-between">
        <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${
          alert.severity === "SEVERE" ? "bg-red-500/20 text-red-400" : alert.severity === "MODERATE" ? "bg-amber-500/20 text-amber-400" : "bg-slate-500/20 text-slate-400"
        }`}>{alert.severity}</span>
        <ArrowUpRight className="h-3 w-3 text-on-surface-variant" />
      </div>
      <p className="mt-2 text-sm font-medium text-on-surface truncate">{alert.location.summary}</p>
      <p className="mt-1 text-[10px] text-on-surface-variant">{alert.probability}% probability · {alert.confidence}</p>
    </Link>
  );
}

export function Dashboard(): JSX.Element {
  const forecast = useForecast();
  const { event } = useSelectedEvent();
  const setLeads = useTimeline((s) => s.setLeads);
  const lead = useTimeline(currentLead);
  const playing = useTimeline((s) => s.playing);
  const leads = useTimeline((s) => s.leads);
  const index = useTimeline((s) => s.index);
  const layers = useUi((s) => s.layers);
  const compare = useUi((s) => s.compare);
  const single = useUi((s) => s.single);
  const ws = useLive((s) => s.status);
  const qc = useQueryClient();

  useEffect(() => { if (forecast.data) setLeads(forecast.data.lead_hours); }, [forecast.data, setLeads]);

  const traj = useTrajectory(event?.id ?? null);
  const impact = useImpact(event?.id ?? null, lead);
  const coarse = useField({ product: "forecast", variable: "tp", lead });
  const fine = useField({ product: "downscaled", variable: "tp", method: "bicubic_conservative", lead });
  const truth = useField({ product: "truth", variable: "tp", lead, enabled: compare === "single" && single === "truth" });
  const anomaly = useField({ product: "anomaly", variable: "anomaly", lead, enabled: layers.anomaly });
  const u10 = useField({ product: "forecast", variable: "u10", lead, enabled: layers.wind });
  const v10 = useField({ product: "forecast", variable: "v10", lead, enabled: layers.wind });
  const countries = useGeoJson("countries_domain.geojson");
  const states = useGeoJson<{ name: string }>("india_states_domain.geojson");
  const events = useEvents({});
  const alerts = useAlerts();

  useEffect(() => {
    const next = leads[index + 1];
    if (!playing || next === undefined) return;
    for (const [product, method] of [["forecast", undefined], ["downscaled", "bicubic_conservative"]] as const) {
      void qc.prefetchQuery({ queryKey: ["field", product, "tp", next, method ?? null], staleTime: 600_000, queryFn: async () => decodeField((await apiGet<FieldPayload>("/fields", { product, variable: "tp", lead_hours: next, method })).data) });
    }
  }, [playing, index, leads, qc]);

  const domain = useMemo<[number, number, number, number]>(() => coarse.data?.payload.bounds ?? [80, 12, 92, 24], [coarse.data]);
  const partial = [coarse, fine].some((q) => q.isError) ? "a raster layer failed to load; other layers are still shown" : countries.isError ? "boundary layer unavailable" : null;
  const wind = layers.wind && u10.data && v10.data ? { u: u10.data, v: v10.data } : undefined;
  const validTimes = forecast.data?.valid_times ?? [];

  const activeEvents = events.data?.filter((e) => e.severity === "SEVERE") ?? [];
  const activeAlerts = alerts.data ?? [];

  return (
    <div className="flex h-full min-h-[760px] flex-col xl:min-h-0" data-testid="dashboard">
      <h1 className="sr-only">Mission Control: extreme weather tracking dashboard</h1>

      {/* Stats Bar */}
      <div className="grid grid-cols-2 gap-3 border-b border-outline-variant/40 bg-surface-container-low p-4 lg:grid-cols-4">
        <StatCard icon={Cloud} label="Active Events" value={fmtInt(events.data?.length)} sub={`${activeEvents.length} severe`} color="text-cyan-400" />
        <StatCard icon={AlertTriangle} label="Active Alerts" value={fmtInt(activeAlerts.length)} sub="analytical alerts" color="text-amber-400" />
        <StatCard icon={Droplets} label="Peak Precipitation" value={event ? `${fmt(event.peak_intensity.value, 0)} mm` : "---"} sub={event ? event.peak_intensity.unit : "no event selected"} color="text-blue-400" />
        <StatCard icon={Wind} label="Pipeline" value={ws === "open" ? "LIVE" : "OFFLINE"} sub={`Lead: T+${lead ?? 0}h`} color={ws === "open" ? "text-emerald-400" : "text-red-400"} />
      </div>

      <div className="flex min-h-0 flex-1 flex-col xl:flex-row">
        {/* Left Sidebar - Layers */}
        <aside aria-label="Layers and tools" className="hidden w-64 shrink-0 border-r border-outline-variant/40 xl:block">
          <LayerPanel />
        </aside>

        {/* Map */}
        <div className="flex min-h-[420px] min-w-0 flex-1 flex-col">
          <AsyncBoundary query={coarse} label="weather map" className="h-full" skeleton={<div className="skeleton h-[420px] w-full" />} partialNote={partial}>
            {() => (
              <MapView lead={lead ?? 0} domain={domain} coarse={coarse.data} fine={fine.data} truth={truth.data} anomaly={anomaly.data} wind={wind}
                trajectory={traj.data} impact={layers.impact ? impact.data : undefined} countries={layers.boundaries ? countries.data : undefined} states={layers.boundaries ? states.data : undefined} />
            )}
          </AsyncBoundary>
        </div>

        {/* Right Panels */}
        <div className="w-full shrink-0 space-y-2 overflow-y-auto border-l border-outline-variant/40 bg-surface p-2 xl:w-[420px]" aria-label="Analysis panels">
          {/* Quick Alerts */}
          {activeAlerts.length > 0 && (
            <div className="rounded-xl border border-outline-variant/40 bg-surface-container-lowest p-3">
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-xs font-semibold text-on-surface uppercase tracking-wide">Active Alerts</h3>
                <Link to="/alerts" className="text-[10px] text-primary hover:underline">View all</Link>
              </div>
              <div className="space-y-2">
                {activeAlerts.slice(0, 3).map((a) => (
                  <QuickAlertCard key={a.id} alert={a} />
                ))}
              </div>
            </div>
          )}

          <EventPanel lead={lead} />
          <ExplainPanel eventId={event?.id ?? null} lead={lead} />
          <EnsemblePanel eventId={event?.id ?? null} lead={lead} />
          <DownscalePanel eventId={event?.id ?? null} />
          <PhysicsPanel eventId={event?.id ?? null} lead={lead} />
          <AlertPanel />
          <ProvenancePanel event={event} validTime={lead !== undefined ? validTimes[index] : undefined} />
        </div>
      </div>

      <TimelineBar validTimes={validTimes} peakLead={event?.peak_lead_hours} extrapolationHours={forecast.data?.extrapolation_hours ?? []} />
    </div>
  );
}
