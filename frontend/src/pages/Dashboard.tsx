import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowUpRight,
  Cloud,
  Wind,
  Droplets,
  Layers,
  BarChart3,
  X,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightClose,
  PanelRightOpen,
} from "lucide-react";

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
    <div className="rounded-xl border border-outline-variant/40 bg-surface-container-lowest p-3 transition hover:border-primary/30 shadow-xs">
      <div className="flex items-center gap-2.5">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10">
          <Icon className={`h-4.5 w-4.5 ${color}`} />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-[10px] font-semibold text-on-surface-variant uppercase tracking-wider truncate">{label}</p>
          <p className="mt-0.5 text-base font-bold text-on-surface font-mono truncate">{value}</p>
          {sub && <p className="text-[9px] text-on-surface-variant truncate">{sub}</p>}
        </div>
      </div>
    </div>
  );
}

function QuickAlertCard({ alert }: { alert: { id: string; severity: string; location: { summary: string }; probability: number; confidence: string } }) {
  const sevColor = alert.severity === "SEVERE" ? "border-red-500/40 bg-red-500/5" : alert.severity === "MODERATE" ? "border-amber-500/40 bg-amber-500/5" : "border-slate-500/40 bg-slate-500/5";
  return (
    <Link to="/alerts" className={`block rounded-lg border p-2.5 transition hover:opacity-85 ${sevColor}`}>
      <div className="flex items-center justify-between">
        <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[9px] font-bold uppercase ${
          alert.severity === "SEVERE" ? "bg-red-500/20 text-red-500 dark:text-red-400" : alert.severity === "MODERATE" ? "bg-amber-500/20 text-amber-600 dark:text-amber-400" : "bg-slate-500/20 text-slate-500 dark:text-slate-400"
        }`}>{alert.severity}</span>
        <ArrowUpRight className="h-3 w-3 text-on-surface-variant" />
      </div>
      <p className="mt-1.5 text-xs font-semibold text-on-surface truncate">{alert.location.summary}</p>
      <p className="mt-0.5 text-[10px] text-on-surface-variant">{alert.probability}% probability · {alert.confidence}</p>
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

  const [layerPanelOpen, setLayerPanelOpen] = useState(true);
  const [analysisPanelOpen, setAnalysisPanelOpen] = useState(true);
  const [mobileLayersOpen, setMobileLayersOpen] = useState(false);
  const [mobileAnalysisOpen, setMobileAnalysisOpen] = useState(false);

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
  const activeLayerCount = Object.values(layers).filter(Boolean).length;

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden" data-testid="dashboard">
      <h1 className="sr-only">Mission Control: extreme weather tracking dashboard</h1>

      {/* Top Stats Bar */}
      <div className="grid grid-cols-2 gap-2 border-b border-outline-variant/40 bg-surface-container-low p-2.5 sm:gap-3 sm:p-3 md:grid-cols-4 shrink-0">
        <StatCard icon={Cloud} label="Active Events" value={fmtInt(events.data?.length)} sub={`${activeEvents.length} severe`} color="text-cyan-500" />
        <StatCard icon={AlertTriangle} label="Active Alerts" value={fmtInt(activeAlerts.length)} sub="analytical alerts" color="text-amber-500" />
        <StatCard icon={Droplets} label="Peak Precipitation" value={event ? `${fmt(event.peak_intensity.value, 0)} mm` : "---"} sub={event ? event.peak_intensity.unit : "no event selected"} color="text-blue-500" />
        <StatCard icon={Wind} label="Pipeline" value={ws === "open" ? "LIVE" : "OFFLINE"} sub={`Lead: T+${lead ?? 0}h`} color={ws === "open" ? "text-emerald-500" : "text-red-500"} />
      </div>

      {/* Responsive Drawer Toggle Bar (Visible on < xl screens) */}
      <div className="flex xl:hidden items-center justify-between border-b border-outline-variant/40 bg-surface-container-low/70 px-3 py-1.5 shrink-0">
        <button
          type="button"
          onClick={() => setMobileLayersOpen(true)}
          className="flex items-center gap-1.5 rounded-lg border border-outline-variant/60 bg-surface-container-lowest px-2.5 py-1 text-xs font-medium text-on-surface shadow-xs hover:bg-surface-container transition"
        >
          <Layers className="h-3.5 w-3.5 text-primary" />
          <span>Layers & Style</span>
          <span className="rounded-full bg-primary/10 text-primary px-1.5 py-0.2 text-[10px] font-mono font-bold">
            {activeLayerCount}
          </span>
        </button>

        <button
          type="button"
          onClick={() => setMobileAnalysisOpen(true)}
          className="flex items-center gap-1.5 rounded-lg border border-outline-variant/60 bg-surface-container-lowest px-2.5 py-1 text-xs font-medium text-on-surface shadow-xs hover:bg-surface-container transition"
        >
          <BarChart3 className="h-3.5 w-3.5 text-primary" />
          <span>Analysis & Alerts</span>
          {activeAlerts.length > 0 && (
            <span className="rounded-full bg-red-500/15 text-red-500 px-1.5 py-0.2 text-[10px] font-mono font-bold">
              {activeAlerts.length}
            </span>
          )}
        </button>
      </div>

      <div className="flex min-h-0 flex-1 relative overflow-hidden">
        {/* Left Sidebar - Layers (Desktop) */}
        {layerPanelOpen && (
          <aside aria-label="Layers and tools" className="hidden w-64 shrink-0 border-r border-outline-variant/40 xl:flex xl:flex-col relative">
            <LayerPanel />
            <button
              type="button"
              onClick={() => setLayerPanelOpen(false)}
              className="absolute right-2 top-2 z-10 rounded p-1 text-on-surface-variant hover:bg-surface-container hover:text-on-surface"
              title="Collapse layer panel"
            >
              <PanelLeftClose className="h-4 w-4" />
            </button>
          </aside>
        )}

        {!layerPanelOpen && (
          <button
            type="button"
            onClick={() => setLayerPanelOpen(true)}
            className="hidden xl:flex absolute left-2 top-2 z-20 items-center gap-1.5 rounded-lg border border-outline-variant/60 bg-surface-container-lowest/90 backdrop-blur-md px-2.5 py-1.5 text-xs font-medium text-on-surface shadow-md hover:bg-surface-container transition"
            title="Expand layer panel"
          >
            <PanelLeftOpen className="h-4 w-4 text-primary" />
            <span>Layers ({activeLayerCount})</span>
          </button>
        )}

        {/* Map Center Area */}
        <div className="flex min-h-0 min-w-0 flex-1 flex-col relative">
          <AsyncBoundary query={coarse} label="weather map" className="h-full" skeleton={<div className="skeleton h-full w-full" />} partialNote={partial}>
            {() => (
              <MapView lead={lead ?? 0} domain={domain} coarse={coarse.data} fine={fine.data} truth={truth.data} anomaly={anomaly.data} wind={wind}
                trajectory={traj.data} impact={layers.impact ? impact.data : undefined} countries={layers.boundaries ? countries.data : undefined} states={layers.boundaries ? states.data : undefined} />
            )}
          </AsyncBoundary>
        </div>

        {/* Right Panels (Desktop) */}
        {analysisPanelOpen && (
          <div className="hidden xl:block w-[380px] 2xl:w-[420px] shrink-0 space-y-2 overflow-y-auto border-l border-outline-variant/40 bg-surface p-2.5 relative" aria-label="Analysis panels">
            <div className="flex items-center justify-between pb-1">
              <span className="text-[10px] font-bold uppercase tracking-wider text-on-surface-variant">Diagnostics & Telemetry</span>
              <button
                type="button"
                onClick={() => setAnalysisPanelOpen(false)}
                className="rounded p-1 text-on-surface-variant hover:bg-surface-container hover:text-on-surface"
                title="Collapse analysis panel"
              >
                <PanelRightClose className="h-4 w-4" />
              </button>
            </div>

            {/* Quick Alerts */}
            {activeAlerts.length > 0 && (
              <div className="rounded-xl border border-outline-variant/40 bg-surface-container-lowest p-3 shadow-xs">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-xs font-bold text-on-surface uppercase tracking-wide">Active Alerts</h3>
                  <Link to="/alerts" className="text-[10px] text-primary hover:underline font-medium">View all</Link>
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
        )}

        {!analysisPanelOpen && (
          <button
            type="button"
            onClick={() => setAnalysisPanelOpen(true)}
            className="hidden xl:flex absolute right-16 top-2 z-20 items-center gap-1.5 rounded-lg border border-outline-variant/60 bg-surface-container-lowest/90 backdrop-blur-md px-2.5 py-1.5 text-xs font-medium text-on-surface shadow-md hover:bg-surface-container transition"
            title="Expand analysis panel"
          >
            <PanelRightOpen className="h-4 w-4 text-primary" />
            <span>Analysis</span>
          </button>
        )}

        {/* Mobile/Tablet Layers Drawer Overlay */}
        {mobileLayersOpen && (
          <div className="fixed inset-0 z-50 xl:hidden">
            <div className="absolute inset-0 bg-black/50 backdrop-blur-xs" onClick={() => setMobileLayersOpen(false)} />
            <aside className="absolute left-0 top-0 bottom-0 w-72 bg-surface-container-lowest border-r border-outline-variant/40 shadow-2xl flex flex-col">
              <div className="flex h-12 items-center justify-between border-b border-outline-variant/40 px-3 bg-surface-container-low">
                <span className="text-xs font-bold text-on-surface uppercase tracking-wider">Layers & Map Style</span>
                <button onClick={() => setMobileLayersOpen(false)} className="rounded-lg p-1 hover:bg-surface-container text-on-surface-variant">
                  <X className="h-4 w-4" />
                </button>
              </div>
              <div className="flex-1 overflow-y-auto">
                <LayerPanel />
              </div>
            </aside>
          </div>
        )}

        {/* Mobile/Tablet Analysis Drawer Overlay */}
        {mobileAnalysisOpen && (
          <div className="fixed inset-0 z-50 xl:hidden">
            <div className="absolute inset-0 bg-black/50 backdrop-blur-xs" onClick={() => setMobileAnalysisOpen(false)} />
            <aside className="absolute right-0 top-0 bottom-0 w-84 max-w-[85vw] bg-surface border-l border-outline-variant/40 shadow-2xl flex flex-col">
              <div className="flex h-12 items-center justify-between border-b border-outline-variant/40 px-3 bg-surface-container-low">
                <span className="text-xs font-bold text-on-surface uppercase tracking-wider">Analysis & Alerts</span>
                <button onClick={() => setMobileAnalysisOpen(false)} className="rounded-lg p-1 hover:bg-surface-container text-on-surface-variant">
                  <X className="h-4 w-4" />
                </button>
              </div>
              <div className="flex-1 overflow-y-auto p-3 space-y-2">
                {activeAlerts.length > 0 && (
                  <div className="rounded-xl border border-outline-variant/40 bg-surface-container-lowest p-3 shadow-xs">
                    <div className="flex items-center justify-between mb-2">
                      <h3 className="text-xs font-bold text-on-surface uppercase tracking-wide">Active Alerts</h3>
                      <Link to="/alerts" className="text-[10px] text-primary hover:underline font-medium">View all</Link>
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
            </aside>
          </div>
        )}
      </div>

      {/* Timeline Controls Footer */}
      <div className="shrink-0">
        <TimelineBar validTimes={validTimes} peakLead={event?.peak_lead_hours} extrapolationHours={forecast.data?.extrapolation_hours ?? []} />
      </div>
    </div>
  );
}
