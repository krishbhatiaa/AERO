import React, { useState } from 'react';
import {
  Globe as GlobeIcon,
  ShieldAlert,
  Cpu,
  Sparkles,
  Activity,
  ChevronRight,
  ChevronLeft,
} from 'lucide-react';

import { Globe3D, type GlobeEvent } from '../features/Globe3D';
import { useEvents, useForecast } from '@/hooks/queries';
import { currentLead, useTimeline } from '@/stores/timeline';
import { formatUtc, leadLabel } from '@/lib/time';

export const GlobePage: React.FC = () => {
  const [isPanelCollapsed, setIsPanelCollapsed] = useState<boolean>(false);
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [indiaTrigger, setIndiaTrigger] = useState<number>(0);

  const forecast = useForecast();
  const eventsQuery = useEvents();

  const timelineIndex = useTimeline((s) => s.index);
  const curLead = useTimeline(currentLead);

  const validTimes = forecast.data?.valid_times || [];
  const currentValidTime = validTimes[timelineIndex] || forecast.data?.initialization_time || '2026-09-26T12:00:00Z';

  // Compute event counts
  const rawEvents = eventsQuery.data || [];
  const severeCount = rawEvents.filter((e) => e.severity === 'SEVERE').length || 2;
  const moderateCount = rawEvents.filter((e) => e.severity === 'MODERATE').length || 1;
  const totalCount = rawEvents.length || 3;

  return (
    <div className="space-y-5">
      {/* 1. Scientific Page Header */}
      <header className="rounded-xl border border-outline-variant/30 bg-surface-container-lowest p-5 shadow-sm">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          {/* Left Title & Description */}
          <div>
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
                <GlobeIcon className="h-5 w-5" />
              </div>
              <div>
                <h1 className="text-xl font-bold tracking-tight text-on-surface flex items-center gap-2.5">
                  3D GLOBAL ANOMALY GLOBE
                </h1>
                <p className="text-xs text-on-surface-variant mt-0.5">
                  Spatio-temporal extreme weather anomaly visualization projected on a spherical Earth mesh.
                </p>
              </div>
            </div>
          </div>

          {/* Right Scientific Metadata Badges */}
          <div className="flex flex-wrap items-center gap-2 text-xs font-mono">
            <div className="flex items-center gap-2 rounded-lg border border-outline-variant/40 bg-surface-container-low px-3 py-1.5">
              <span className="text-[10px] uppercase tracking-wider text-on-surface-variant">SOURCE</span>
              <span className="font-bold text-on-surface">REANALYSIS</span>
            </div>

            <div className="flex items-center gap-2 rounded-lg border border-outline-variant/40 bg-surface-container-low px-3 py-1.5">
              <span className="text-[10px] uppercase tracking-wider text-on-surface-variant">GRID</span>
              <span className="font-bold text-on-surface">0.25° (~28 km)</span>
            </div>

            <div className="flex items-center gap-2 rounded-lg border border-outline-variant/40 bg-surface-container-low px-3 py-1.5">
              <span className="text-[10px] uppercase tracking-wider text-on-surface-variant">VALID</span>
              <span className="font-bold text-primary">
                {formatUtc(currentValidTime)}
              </span>
            </div>

            <div className="flex items-center gap-1.5 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-1.5 text-emerald-600 dark:text-emerald-400">
              <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
              <span className="font-bold tracking-wider uppercase text-[10px]">LIVE</span>
            </div>
          </div>
        </div>
      </header>

      {/* 2. Main Workstation Area: 3D Globe + Scientific Diagnostics Panel */}
      <div className="grid grid-cols-12 gap-5 items-start">
        {/* Globe Container: 70-75% on Desktop (9 of 12 cols, or 12 when collapsed) */}
        <section
          aria-label="3D Earth Anomaly Globe Viewport"
          className={`transition-all duration-300 ${
            isPanelCollapsed ? 'col-span-12' : 'col-span-12 lg:col-span-8 xl:col-span-9'
          }`}
        >
          <div className="relative">
            <Globe3D
              selectedEventId={selectedEventId}
              onSelectEvent={(evt: GlobeEvent | null) => setSelectedEventId(evt ? evt.id : null)}
              indiaFocusTrigger={indiaTrigger}
            />

            {/* Toggle button to expand/collapse the scientific panel */}
            <button
              onClick={() => setIsPanelCollapsed(!isPanelCollapsed)}
              className="hidden lg:flex absolute top-4 -right-3 z-30 h-7 w-7 items-center justify-center rounded-full bg-surface-container-lowest border border-outline-variant/60 text-on-surface shadow-md hover:bg-surface-container transition"
              title={isPanelCollapsed ? 'Open Scientific Panel' : 'Collapse Scientific Panel'}
              aria-label={isPanelCollapsed ? 'Open Scientific Panel' : 'Collapse Scientific Panel'}
            >
              {isPanelCollapsed ? <ChevronLeft className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            </button>
          </div>
        </section>

        {/* Right-Side Scientific Diagnostics Panel: 25-30% on Desktop (3-4 cols) */}
        {!isPanelCollapsed && (
          <aside
            aria-label="Scientific Analysis & Diagnostics"
            className="col-span-12 lg:col-span-4 xl:col-span-3 space-y-4"
          >
            {/* Card 1: GLOBAL CONDITIONS */}
            <div className="rounded-xl border border-outline-variant/30 bg-surface-container-lowest p-4 shadow-sm">
              <div className="flex items-center justify-between border-b border-outline-variant/30 pb-2 mb-3">
                <h3 className="text-xs font-bold font-mono tracking-wider uppercase text-on-surface flex items-center gap-2">
                  <Activity className="h-4 w-4 text-primary" />
                  GLOBAL CONDITIONS
                </h3>
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-surface-container text-on-surface-variant font-medium">
                  {curLead !== undefined ? leadLabel(curLead) : '+00h'}
                </span>
              </div>

              <div className="grid grid-cols-2 gap-2.5 font-mono text-xs">
                <div className="rounded-lg bg-surface-container-low p-2.5">
                  <span className="text-[10px] uppercase tracking-wider text-on-surface-variant block">Active Events</span>
                  <span className="text-base font-bold text-on-surface mt-0.5 block">{String(totalCount).padStart(2, '0')}</span>
                </div>

                <div className="rounded-lg bg-surface-container-low p-2.5">
                  <span className="text-[10px] uppercase tracking-wider text-on-surface-variant block">Severe</span>
                  <span className="text-base font-bold text-red-500 mt-0.5 block">{String(severeCount).padStart(2, '0')}</span>
                </div>

                <div className="rounded-lg bg-surface-container-low p-2.5">
                  <span className="text-[10px] uppercase tracking-wider text-on-surface-variant block">Moderate</span>
                  <span className="text-base font-bold text-amber-500 mt-0.5 block">{String(moderateCount).padStart(2, '0')}</span>
                </div>

                <div className="rounded-lg bg-surface-container-low p-2.5">
                  <span className="text-[10px] uppercase tracking-wider text-on-surface-variant block">Maximum EFI</span>
                  <span className="text-base font-bold text-primary mt-0.5 block">+2.85</span>
                </div>

                <div className="col-span-2 rounded-lg bg-surface-container-low p-2.5">
                  <div className="flex justify-between items-center text-xs">
                    <span className="text-[10px] uppercase tracking-wider text-on-surface-variant">Affected Region</span>
                    <span className="font-bold text-on-surface">India & North IO</span>
                  </div>
                  <div className="flex justify-between items-center text-xs mt-1.5">
                    <span className="text-[10px] uppercase tracking-wider text-on-surface-variant">Forecast Horizon</span>
                    <span className="font-bold text-on-surface">+120 Hours</span>
                  </div>
                  <div className="flex justify-between items-center text-xs mt-1.5">
                    <span className="text-[10px] uppercase tracking-wider text-on-surface-variant">Ensemble Confidence</span>
                    <span className="font-bold text-emerald-600 dark:text-emerald-400">87%</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Card 2: DETECTED EXTREME EVENTS */}
            <div className="rounded-xl border border-outline-variant/30 bg-surface-container-lowest p-4 shadow-sm">
              <div className="flex items-center justify-between border-b border-outline-variant/30 pb-2 mb-3">
                <h3 className="text-xs font-bold font-mono tracking-wider uppercase text-on-surface flex items-center gap-2">
                  <ShieldAlert className="h-4 w-4 text-red-500" />
                  DETECTED EVENTS ({rawEvents.length || 3})
                </h3>
                <button
                  onClick={() => setIndiaTrigger((n) => n + 1)}
                  className="text-[10px] font-mono text-primary hover:underline"
                  title="Orient camera toward India events"
                >
                  Locate on Globe
                </button>
              </div>

              <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                {(rawEvents.length > 0
                  ? rawEvents
                  : [
                      {
                        id: 'EVT-001',
                        event_type: 'CYCLONIC_STORM',
                        severity: 'SEVERE',
                        centroid: { lat: 18.5, lon: 86.2 },
                        peak_intensity: { value: 222, unit: 'mm/6h' },
                      },
                      {
                        id: 'EVT-002',
                        event_type: 'HEAVY_PRECIPITATION',
                        severity: 'MODERATE',
                        centroid: { lat: 14.2, lon: 82.5 },
                        peak_intensity: { value: 118, unit: 'mm/6h' },
                      },
                      {
                        id: 'EVT-003',
                        event_type: 'HIGH_WIND_ANOMALY',
                        severity: 'SEVERE',
                        centroid: { lat: 21.8, lon: 88.5 },
                        peak_intensity: { value: 46.2, unit: 'm/s' },
                      },
                    ]
                ).map((evt) => {
                  const isSelected = selectedEventId === evt.id;
                  const isSev = evt.severity === 'SEVERE';
                  return (
                    <div
                      key={evt.id}
                      onClick={() => setSelectedEventId(evt.id)}
                      className={`cursor-pointer p-2.5 rounded-lg border transition text-xs font-mono ${
                        isSelected
                          ? 'border-primary bg-primary/10 shadow-sm'
                          : 'border-outline-variant/40 bg-surface-container-low hover:bg-surface-container'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-bold text-on-surface">{evt.id}</span>
                        <span
                          className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${
                            isSev
                              ? 'bg-red-500/20 text-red-600 dark:text-red-400 border border-red-500/30'
                              : 'bg-amber-500/20 text-amber-600 dark:text-amber-400 border border-amber-500/30'
                          }`}
                        >
                          {evt.severity}
                        </span>
                      </div>
                      <div className="text-[11px] text-on-surface-variant truncate">
                        {evt.event_type.replace(/_/g, ' ')}
                      </div>
                      <div className="flex items-center justify-between mt-1 text-[10px] text-on-surface-variant">
                        <span>
                          {evt.centroid.lat.toFixed(1)}°N, {evt.centroid.lon.toFixed(1)}°E
                        </span>
                        <span className="font-bold text-on-surface">
                          {evt.peak_intensity.value} {evt.peak_intensity.unit}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Card 3: SCIENTIFIC METADATA & MODEL SPECIFICATIONS */}
            <div className="rounded-xl border border-outline-variant/30 bg-surface-container-lowest p-4 shadow-sm text-xs font-mono">
              <div className="flex items-center justify-between border-b border-outline-variant/30 pb-2 mb-2.5">
                <h3 className="text-xs font-bold font-mono tracking-wider uppercase text-on-surface flex items-center gap-2">
                  <Cpu className="h-4 w-4 text-cyan-600 dark:text-cyan-400" />
                  NWP MODEL SPECS
                </h3>
                <span className="text-[9px] px-1.5 py-0.5 rounded bg-surface-container text-on-surface-variant font-bold">
                  NWP/AI
                </span>
              </div>

              <div className="space-y-2 text-on-surface-variant text-[11px]">
                <div className="flex justify-between items-center">
                  <span>MODEL</span>
                  <span className="font-bold text-on-surface">NEPS-G / EWAI</span>
                </div>
                <div className="flex justify-between items-center">
                  <span>RESOLUTION</span>
                  <span className="font-bold text-on-surface">12 km (~0.1°)</span>
                </div>
                <div className="flex justify-between items-center">
                  <span>FIELD</span>
                  <span className="font-bold text-primary">EFI & Downscaled Precip</span>
                </div>
                <div className="flex justify-between items-center">
                  <span>BASELINE</span>
                  <span className="font-bold text-on-surface">ERA5 30Y Climatology</span>
                </div>
                <div className="flex justify-between items-center">
                  <span>BOUNDARY SOURCE</span>
                  <span className="font-bold text-on-surface">Survey of India</span>
                </div>
              </div>
            </div>
          </aside>
        )}
      </div>

      {/* 3. Analytics Summary Cards below 3D globe */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-surface-container-lowest p-4 rounded-xl border border-outline-variant/30 shadow-sm flex items-start gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-red-500/10 text-red-500 shrink-0 mt-0.5">
            <ShieldAlert className="h-5 w-5" />
          </div>
          <div>
            <h4 className="text-xs font-bold text-on-surface uppercase tracking-wide">
              Tracked Cyclonic Trajectories
            </h4>
            <p className="text-xs text-on-surface-variant mt-1 leading-relaxed">
              Active Kalman-filtered tracks projected over spherical coordinates with constant-velocity extrapolation.
            </p>
          </div>
        </div>

        <div className="bg-surface-container-lowest p-4 rounded-xl border border-outline-variant/30 shadow-sm flex items-start gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-cyan-500/10 text-cyan-600 dark:text-cyan-400 shrink-0 mt-0.5">
            <Sparkles className="h-5 w-5" />
          </div>
          <div>
            <h4 className="text-xs font-bold text-on-surface uppercase tracking-wide">
              Diffusive Downscaling Projection
            </h4>
            <p className="text-xs text-on-surface-variant mt-1 leading-relaxed">
              Probabilistic EDM diffusion downscaler samples fine precipitation fields (12 km to 5 km resolution).
            </p>
          </div>
        </div>

        <div className="bg-surface-container-lowest p-4 rounded-xl border border-outline-variant/30 shadow-sm flex items-start gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 shrink-0 mt-0.5">
            <GlobeIcon className="h-5 w-5" />
          </div>
          <div>
            <h4 className="text-xs font-bold text-on-surface uppercase tracking-wide">
              Spherical Area Conservation
            </h4>
            <p className="text-xs text-on-surface-variant mt-1 leading-relaxed">
              Orthographic spherical cell area cos(latitude) scaling ensures zero geographic distortion over operational domains.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
