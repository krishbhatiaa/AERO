import { Crosshair, Maximize, Printer, ZoomIn, ZoomOut } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { ControlButton } from "@/components/ControlButton";
import { DataKindBadge } from "@/components/DataKindBadge";
import { useSize } from "@/hooks/useSize";
import { ANOMALY_STOPS, PRECIP_STOPS } from "@/lib/colors";
import { sampleField, type DecodedField } from "@/lib/field";
import { fitView, formatLat, formatLon, haversineKm, panBy, project, unproject, zoomAt, type View } from "@/lib/geo";
import { leadLabel } from "@/lib/time";
import { clamp, fmt } from "@/lib/utils";
import { useUi } from "@/stores/ui";
import type { FeatureCollection, ImpactData, TrajectoryData } from "@/types/api";

import { Legend } from "./Legend";
import { LandLayer, MapOverlay, WorldLandLayer } from "./MapOverlay";
import { RasterCanvas } from "./RasterCanvas";

interface Props {
  lead: number;
  domain: [number, number, number, number];
  coarse?: DecodedField;
  fine?: DecodedField;
  truth?: DecodedField;
  anomaly?: DecodedField;
  wind?: { u: DecodedField; v: DecodedField };
  trajectory?: TrajectoryData;
  impact?: ImpactData;
  countries?: FeatureCollection;
  states?: FeatureCollection<{ name: string }>;
}

const NICE_KM = [10, 25, 50, 100, 250, 500];

function resLabel(f?: DecodedField): string {
  return f ? `${f.payload.resolution_km.north_south.toFixed(1)} km` : "...";
}

export function MapView({ lead, domain, coarse, fine, truth, anomaly, wind, trajectory, impact, countries, states }: Props): JSX.Element {
  const [ref, size, measured] = useSize<HTMLDivElement>();
  const layers = useUi((s) => s.layers);
  const compare = useUi((s) => s.compare);
  const single = useUi((s) => s.single);
  const tool = useUi((s) => s.tool);
  const [view, setView] = useState<View>(() => fitView(domain, { w: 800, h: 520 }));
  const [wipeUser, setWipeUser] = useState<number | null>(null);
  const [measure, setMeasure] = useState<[number, number][]>([]);
  const [probe, setProbe] = useState<[number, number] | null>(null);
  const [showHelp, setShowHelp] = useState(false);
  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const fitted = useRef(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (measured && !fitted.current) {
      setView(fitView(domain, size));
      fitted.current = true;
    }
  }, [measured, size, domain]);
  useEffect(() => { if (tool !== "measure") setMeasure([]); if (tool !== "probe") setProbe(null); }, [tool]);

  const reset = useCallback(() => setView(fitView(domain, size)), [domain, size]);
  const recenter = useCallback(() => {
    const c = trajectory?.features.find((f) => f.properties.kind === "tracked_point" && f.properties.lead_hours === lead);
    if (c?.geometry.type === "Point") setView((v) => ({ ...v, lon: c.geometry.type === "Point" ? c.geometry.coordinates[0] : v.lon, lat: c.geometry.type === "Point" ? c.geometry.coordinates[1] : v.lat, zoom: Math.max(v.zoom, 60) }));
  }, [trajectory, lead]);

  const handleFullscreen = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    if (document.fullscreenElement) {
      document.exitFullscreen();
    } else {
      el.requestFullscreen();
    }
  }, []);

  const handleScreenshot = useCallback(() => {
    const canvas = containerRef.current?.querySelector("canvas");
    if (!canvas) return;
    const link = document.createElement("a");
    link.download = `extreme-weather-map-lead${lead}.png`;
    link.href = canvas.toDataURL("image/png");
    link.click();
  }, [lead]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const onWheel = (e: WheelEvent): void => {
      e.preventDefault();
      const r = el.getBoundingClientRect();
      setView((v) => zoomAt(v, size, e.clientX - r.left, e.clientY - r.top, e.deltaY < 0 ? 1.15 : 1 / 1.15));
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [ref, size]);

  const local = (e: React.PointerEvent): [number, number] => {
    const r = ref.current?.getBoundingClientRect();
    return [e.clientX - (r?.left ?? 0), e.clientY - (r?.top ?? 0)];
  };
  const onPointerDown = (e: React.PointerEvent): void => {
    if (e.button !== 0) return;
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    const [x, y] = local(e);
    drag.current = { x, y, moved: false };
  };
  const onPointerMove = (e: React.PointerEvent): void => {
    const [x, y] = local(e);
    const [lon, lat] = unproject(view, size, x, y);
    useUi.getState().setCursor({ lat, lon });
    const d = drag.current;
    if (!d) return;
    if (!d.moved && Math.hypot(x - d.x, y - d.y) < 4) return;
    d.moved = true;
    setView((v) => panBy(v, x - d.x, y - d.y));
    d.x = x;
    d.y = y;
  };
  const onPointerUp = (e: React.PointerEvent): void => {
    const d = drag.current;
    drag.current = null;
    if (!d || d.moved) return;
    const [x, y] = local(e);
    const [lon, lat] = unproject(view, size, x, y);
    if (tool === "probe") setProbe([lon, lat]);
    if (tool === "measure") setMeasure((m) => (m.length >= 2 ? [[lon, lat]] : [...m, [lon, lat]]));
  };
  const onKeyDown = (e: React.KeyboardEvent): void => {
    const step = 40;
    const map: Record<string, () => void> = {
      ArrowLeft: () => setView((v) => panBy(v, step, 0)), ArrowRight: () => setView((v) => panBy(v, -step, 0)),
      ArrowUp: () => setView((v) => panBy(v, 0, step)), ArrowDown: () => setView((v) => panBy(v, 0, -step)),
      "+": () => setView((v) => zoomAt(v, size, size.w / 2, size.h / 2, 1.25)), "=": () => setView((v) => zoomAt(v, size, size.w / 2, size.h / 2, 1.25)),
      "-": () => setView((v) => zoomAt(v, size, size.w / 2, size.h / 2, 0.8)), "0": reset,
      f: handleFullscreen, s: handleScreenshot, "?": () => setShowHelp(!showHelp),
    };
    const fn = map[e.key];
    if (fn) { e.preventDefault(); fn(); }
  };

  const wipeDrag = useRef(false);
  const onWipeDown = (e: React.PointerEvent): void => { e.stopPropagation(); e.currentTarget.setPointerCapture(e.pointerId); wipeDrag.current = true; };
  const onWipeMove = (e: React.PointerEvent): void => {
    if (!wipeDrag.current) return;
    const r = ref.current?.getBoundingClientRect();
    if (r) setWipeUser(clamp((e.clientX - r.left) / r.width, 0.03, 0.97));
  };
  const onWipeKey = (e: React.KeyboardEvent): void => {
    if (e.key === "ArrowLeft") { e.preventDefault(); setWipeUser(clamp(wipe - 0.05, 0.03, 0.97)); }
    if (e.key === "ArrowRight") { e.preventDefault(); setWipeUser(clamp(wipe + 0.05, 0.03, 0.97)); }
  };

  const split = compare === "split";
  const centroid = trajectory?.features.find((f) => f.properties.kind === "tracked_point" && f.properties.lead_hours === lead);
  const autoWipe = centroid && centroid.geometry.type === "Point" ? clamp(project(view, size, centroid.geometry.coordinates[0], centroid.geometry.coordinates[1])[0] / size.w, 0.08, 0.92) : 0.5;
  const wipe = wipeUser ?? autoWipe;
  const single_ = single === "coarse" ? coarse : single === "truth" ? truth : fine;
  const kmPerPx = 111.195 / view.zoom;
  const nice = NICE_KM.find((k) => k / kmPerPx >= 60) ?? 500;
  const measureKm = measure.length === 2 ? haversineKm(measure[0]![1], measure[0]![0], measure[1]![1], measure[1]![0]) : null;
  const probeVals = probe && {
    coarse: coarse ? sampleField(coarse, probe[0], probe[1]) : null,
    fine: fine ? sampleField(fine, probe[0], probe[1]) : null,
    truth: truth ? sampleField(truth, probe[0], probe[1]) : null,
    score: anomaly ? sampleField(anomaly, probe[0], probe[1]) : null,
  };
  const summary = `Map of synthetic precipitation at ${leadLabel(lead)}. ` + (centroid && centroid.geometry.type === "Point" ? `Event centroid at ${formatLat(centroid.geometry.coordinates[1])}, ${formatLon(centroid.geometry.coordinates[0])}.` : "No event centroid at this lead.");

  return (
    <div ref={containerRef} className="relative h-full w-full">
      <div
        ref={ref}
        role="application"
        aria-label="Interactive weather map. Arrow keys pan, plus and minus zoom, zero resets."
        aria-describedby="map-summary"
        tabIndex={0}
        data-testid="map-view"
        onKeyDown={onKeyDown}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerLeave={() => useUi.getState().setCursor(null)}
        className={`relative h-full min-h-[360px] w-full select-none overflow-hidden bg-[rgb(var(--map-sea))] ${tool === "pan" ? "cursor-grab active:cursor-grabbing" : "cursor-crosshair"}`}
      >
        <p id="map-summary" className="sr-only">{summary}</p>
        <div className="grid-bg absolute inset-0 opacity-40" aria-hidden />
        <WorldLandLayer view={view} size={size} />
        {layers.boundaries && <LandLayer view={view} size={size} countries={countries} />}
        <RasterCanvas field={split ? coarse : single_} stops={PRECIP_STOPS} view={view} size={size} testId="raster-left" />
        {split && <div className="absolute inset-0" style={{ clipPath: `inset(0 0 0 ${wipe * 100}%)` }}><RasterCanvas field={fine} stops={PRECIP_STOPS} view={view} size={size} testId="raster-right" /></div>}
        {layers.anomaly && <RasterCanvas field={anomaly} stops={ANOMALY_STOPS} view={view} size={size} opacity={0.75} />}
        <MapOverlay view={view} size={size} layers={layers} lead={lead} countries={countries} states={states} trajectory={trajectory} impact={impact} coarse={coarse} wind={wind} measure={measure} probe={probe} />

        {split && (
          <div className="pointer-events-none absolute inset-y-0 z-10 w-0.5 bg-primary shadow" style={{ left: `${wipe * 100}%` }}>
            <div
              role="slider" tabIndex={0} aria-label="Comparison divider. Left: coarse forecast. Right: baseline fine grid." aria-orientation="horizontal"
              aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(wipe * 100)} aria-valuetext={`${Math.round(wipe * 100)} percent coarse`}
              onPointerDown={onWipeDown} onPointerMove={onWipeMove} onPointerUp={() => { wipeDrag.current = false; }} onKeyDown={onWipeKey}
              className="pointer-events-auto absolute top-1/2 -left-3 flex h-6 w-6 -translate-y-1/2 cursor-ew-resize items-center justify-center rounded-full bg-primary text-on-primary shadow-md"
            ><span aria-hidden className="text-[11px] font-bold">{"<->"}</span></div>
          </div>
        )}

        <div className="pointer-events-none absolute left-2 right-16 top-2 z-10 flex flex-wrap items-start justify-between gap-2">
          <div className="glass pointer-events-auto flex max-w-sm flex-col gap-1 rounded border border-outline-variant/60 p-2 shadow">
            <div className="flex items-center justify-between gap-2 text-label-header uppercase text-on-surface-variant"><span className="whitespace-nowrap">Coordinate probe</span><span className="whitespace-nowrap font-mono text-primary">EQUIRECT · 18°N</span></div>
            <UseCursor />
            {probeVals && (
              <dl className="grid grid-cols-2 gap-x-3 font-mono text-label-num-md" data-testid="probe-readout">
                <dt className="text-on-surface-variant">Coarse tp</dt><dd>{fmt(probeVals.coarse)} mm/6h</dd>
                <dt className="text-on-surface-variant">Baseline tp</dt><dd>{fmt(probeVals.fine)} mm/6h</dd>
                {probeVals.truth !== null && (<><dt className="text-on-surface-variant">Synthetic truth</dt><dd>{fmt(probeVals.truth)} mm/6h</dd></>)}
                {probeVals.score !== null && (<><dt className="text-on-surface-variant">Anomaly score</dt><dd>{fmt(probeVals.score, 3)}</dd></>)}
              </dl>
            )}
            {measureKm !== null && <div className="font-mono text-label-num-md" data-testid="measure-readout">Distance: <b>{measureKm.toFixed(1)} km</b> (great-circle)</div>}
            {tool === "probe" && !probe && <div className="text-body-xs text-on-surface-variant">Click the map to read values.</div>}
            {tool === "measure" && measure.length < 2 && <div className="text-body-xs text-on-surface-variant">Click two points to measure.</div>}
          </div>
          {split ? (
            <div className="flex gap-2">
              <div className="glass flex flex-col items-start gap-1 rounded border border-outline-variant/60 p-1.5 shadow"><span className="text-label-header uppercase">Coarse forecast · {resLabel(coarse)}</span><DataKindBadge kind="SYNTHETIC_DEMO" compact /></div>
              <div className="glass flex flex-col items-start gap-1 rounded border border-outline-variant/60 p-1.5 shadow"><span className="text-label-header uppercase">Baseline · {resLabel(fine)} · interpolation, no ML</span><DataKindBadge kind="SYNTHETIC_DEMO" compact /></div>
            </div>
          ) : (
            <div className="glass flex flex-col items-start gap-1 rounded border border-outline-variant/60 p-1.5 shadow">
              <span className="text-label-header uppercase">{single === "coarse" ? `Coarse forecast · ${resLabel(coarse)}` : single === "truth" ? `Synthetic fine truth · ${resLabel(truth)}` : `Baseline interpolation · ${resLabel(fine)} · no ML`}</span>
              <DataKindBadge kind="SYNTHETIC_DEMO" compact />
            </div>
          )}
        </div>

        <div className="absolute right-2 top-2 z-10 flex flex-col gap-1 rounded border border-outline-variant/60 bg-surface-container-lowest/95 p-1 shadow">
          <ControlButton label="Zoom in" icon={ZoomIn} variant="ghost" size="sm" tooltip="Zoom in (+)" onClick={() => setView((v) => zoomAt(v, size, size.w / 2, size.h / 2, 1.3))} />
          <ControlButton label="Zoom out" icon={ZoomOut} variant="ghost" size="sm" tooltip="Zoom out (-)" onClick={() => setView((v) => zoomAt(v, size, size.w / 2, size.h / 2, 1 / 1.3))} />
          <ControlButton label="Reset view" icon={Maximize} variant="ghost" size="sm" tooltip="Reset view (0)" onClick={reset} />
          <ControlButton label="Recenter on event" icon={Crosshair} variant="ghost" size="sm" tooltip="Recenter on the event at this lead time" disabled={!centroid} disabledReason="No event is tracked at this lead time" onClick={recenter} />
          <ControlButton label="Export screenshot" icon={Printer} variant="ghost" size="sm" tooltip="Export map as PNG (S)" onClick={handleScreenshot} />
        </div>

        <div className="pointer-events-none absolute bottom-2 left-2 z-10 rounded border border-outline-variant/60 bg-surface-container-lowest/95 px-2 py-1 shadow" aria-hidden>
          <div className="h-[3px] border-x border-on-surface" style={{ width: nice / kmPerPx, background: "linear-gradient(90deg, rgb(var(--c-on-surface)) 50%, transparent 50%)", backgroundSize: "50% 100%" }} />
          <div className="font-mono text-[9px]">{nice} km</div>
        </div>
        <div className="pointer-events-none absolute bottom-2 right-2 z-10"><Legend showAnomaly={layers.anomaly} /></div>

        {showHelp && (
          <div className="absolute left-1/2 top-1/2 z-20 -translate-x-1/2 -translate-y-1/2 rounded border border-outline-variant/60 bg-surface-container-lowest/95 p-4 shadow-lg">
            <div className="mb-2 text-label-header uppercase text-on-surface-variant">Keyboard Shortcuts</div>
            <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-label-num-sm">
              <dt className="text-on-surface-variant">Pan</dt><dd>Arrow keys</dd>
              <dt className="text-on-surface-variant">Zoom in</dt><dd>+ / =</dd>
              <dt className="text-on-surface-variant">Zoom out</dt><dd>-</dd>
              <dt className="text-on-surface-variant">Reset</dt><dd>0</dd>
              <dt className="text-on-surface-variant">Fullscreen</dt><dd>F</dd>
              <dt className="text-on-surface-variant">Screenshot</dt><dd>S</dd>
              <dt className="text-on-surface-variant">Help</dt><dd>?</dd>
            </dl>
            <button type="button" onClick={() => setShowHelp(false)} className="mt-3 rounded border border-outline-variant bg-surface-container-low px-2 py-1 text-label-num-sm">Close</button>
          </div>
        )}
      </div>
    </div>
  );
}

function UseCursor(): JSX.Element {
  const c = useUi((s) => s.cursor);
  return (
    <div className="font-mono text-label-num-md" data-testid="cursor-readout">
      <span className="text-on-surface-variant">LAT/LON </span>
      <span className="font-medium">{c ? `${formatLat(c.lat)}, ${formatLon(c.lon)}` : "--- move over the map ---"}</span>
    </div>
  );
}
