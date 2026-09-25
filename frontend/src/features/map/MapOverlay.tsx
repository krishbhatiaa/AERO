import { useMemo } from "react";
import { feature as topojsonFeature } from "topojson-client";
import type { Topology } from "topojson-specification";
import worldLand from "world-atlas/land-110m.json";

import { dataToScreenTransform, geometryToPath, project, type Size, type View } from "@/lib/geo";
import type { DecodedField } from "@/lib/field";
import type { Feature, FeatureCollection, Geometry, ImpactData, TrackFeatureProps, TrajectoryData } from "@/types/api";
import type { Layers } from "@/stores/ui";
import { leadLabel } from "@/lib/time";

const NICE = [0.25, 0.5, 1, 2, 5, 10];
const WORLD_LAND = topojsonFeature(worldLand as Topology, "land") as unknown as { features: Array<{ geometry: Geometry }> };

function graticuleStep(v: View): number {
  const target = 70 / v.zoom; // degrees per ~70 px
  return NICE.find((n) => n >= target) ?? 10;
}

function ringCenter(g: Geometry): [number, number] | null {
  const rings = g.type === "Polygon" ? [g.coordinates[0]] : g.type === "MultiPolygon" ? g.coordinates.map((p) => p[0]) : [];
  let best: [number, number][] | null = null;
  let bestSpan = -1;
  for (const r of rings) {
    if (!r) continue;
    const xs = r.map((c) => c[0]), ys = r.map((c) => c[1]);
    const span = (Math.max(...xs) - Math.min(...xs)) * (Math.max(...ys) - Math.min(...ys));
    if (span > bestSpan) { bestSpan = span; best = r as [number, number][]; }
  }
  if (!best) return null;
  const xs = best.map((c) => c[0]), ys = best.map((c) => c[1]);
  return [(Math.min(...xs) + Math.max(...xs)) / 2, (Math.min(...ys) + Math.max(...ys)) / 2];
}

/** Land fill drawn beneath the rasters so land and sea are distinguishable. */
export function WorldLandLayer({ view, size }: { view: View; size: Size }): JSX.Element {
  const d = useMemo(() => view.zoom <= 18 ? WORLD_LAND.features.map((f) => geometryToPath(f.geometry as Geometry)).join("") : "", [view.zoom]);
  return (
    <svg className="pointer-events-none absolute inset-0 h-full w-full" width={size.w} height={size.h} aria-hidden data-testid="world-land-layer">
      <g transform={dataToScreenTransform(view, size)}><path d={d} fill="rgb(var(--map-land))" fillOpacity={0.42} stroke="rgb(var(--c-outline))" strokeOpacity={0.4} strokeWidth={0.35} /></g>
    </svg>
  );
}

export function LandLayer({ view, size, countries }: { view: View; size: Size; countries?: FeatureCollection }): JSX.Element {
  const d = useMemo(() => (countries ? countries.features.map((f) => geometryToPath(f.geometry)).join("") : ""), [countries]);
  return (
    <svg className="pointer-events-none absolute inset-0 h-full w-full" width={size.w} height={size.h} aria-hidden data-testid="land-layer">
      <g transform={dataToScreenTransform(view, size)}><path d={d} fill="rgb(var(--map-land))" fillOpacity={0.9} stroke="none" /></g>
    </svg>
  );
}

interface Props {
  view: View;
  size: Size;
  layers: Layers;
  lead: number;
  countries?: FeatureCollection;
  states?: FeatureCollection<{ name: string }>;
  trajectory?: TrajectoryData;
  impact?: ImpactData;
  coarse?: DecodedField;
  wind?: { u: DecodedField; v: DecodedField };
  measure: [number, number][];
  probe: [number, number] | null;
}

/** Vector overlay. Paths live in lon/lat data space under one transform, so pan/zoom never recomputes geometry. */
export function MapOverlay({ view, size, layers, lead, countries, states, trajectory, impact, coarse, wind, measure, probe }: Props): JSX.Element {
  const transform = dataToScreenTransform(view, size);
  const countriesPath = useMemo(() => (countries ? countries.features.map((f) => geometryToPath(f.geometry)).join("") : ""), [countries]);
  const statesPath = useMemo(() => (states ? states.features.map((f) => geometryToPath(f.geometry)).join("") : ""), [states]);
  const labels = useMemo(() => (states ? states.features.map((f) => ({ name: f.properties.name, c: ringCenter(f.geometry) })).filter((l): l is { name: string; c: [number, number] } => !!l.c) : []), [states]);
  const feats = trajectory?.features ?? [];
  const by = (k: TrackFeatureProps["kind"]): Feature<TrackFeatureProps>[] => feats.filter((f) => f.properties.kind === k);
  const tracked = by("tracked")[0], extrap = by("extrapolation")[0], env = by("uncertainty_envelope")[0], members = by("ensemble_members")[0];
  const points = by("tracked_point"), exPoints = by("extrapolated_point");
  const cur = points.find((p) => p.properties.lead_hours === lead);

  const step = graticuleStep(view);
  const tl = { lon: view.lon - size.w / 2 / (view.zoom * Math.cos((18 * Math.PI) / 180)), lat: view.lat + size.h / 2 / view.zoom };
  const br = { lon: view.lon + size.w / 2 / (view.zoom * Math.cos((18 * Math.PI) / 180)), lat: view.lat - size.h / 2 / view.zoom };
  const lons: number[] = [], lats: number[] = [];
  for (let x = Math.ceil(tl.lon / step) * step; x <= br.lon; x += step) lons.push(x);
  for (let y = Math.ceil(br.lat / step) * step; y <= tl.lat; y += step) lats.push(y);
  const gLines = lons.map((x) => `M${x} ${br.lat - 5}L${x} ${tl.lat + 5}`).join("") + lats.map((y) => `M${tl.lon - 5} ${y}L${br.lon + 5} ${y}`).join("");

  const arrows: JSX.Element[] = [];
  if (layers.wind && wind && coarse) {
    const [w, s, e, n] = coarse.payload.bounds;
    const k = Math.max(4, Math.round(60 / (view.zoom * 0.1)));
    for (let r = 0; r < coarse.ny; r += k) {
      for (let c = 0; c < coarse.nx; c += k) {
        const u = wind.u.values[r * coarse.nx + c] ?? 0, v = wind.v.values[r * coarse.nx + c] ?? 0;
        const sp = Math.hypot(u, v);
        if (sp < 8) continue;
        const lon = w + ((c + 0.5) / coarse.nx) * (e - w), lat = s + ((r + 0.5) / coarse.ny) * (n - s);
        const [x, y] = project(view, size, lon, lat);
        const len = Math.min(22, 4 + sp * 0.6), ang = Math.atan2(-v, u);
        const x2 = x + Math.cos(ang) * len, y2 = y + Math.sin(ang) * len;
        arrows.push(<path key={`${r}-${c}`} d={`M${x} ${y}L${x2} ${y2}M${x2} ${y2}l${-4 * Math.cos(ang - 0.5)} ${-4 * Math.sin(ang - 0.5)}M${x2} ${y2}l${-4 * Math.cos(ang + 0.5)} ${-4 * Math.sin(ang + 0.5)}`} stroke="rgb(var(--c-on-surface))" strokeOpacity={0.55} strokeWidth={0.9} fill="none" />);
      }
    }
  }

  const pt = (f: Feature<TrackFeatureProps>): [number, number] => {
    const c = (f.geometry as { coordinates: [number, number] }).coordinates;
    return project(view, size, c[0], c[1]);
  };

  return (
    <svg className="pointer-events-none absolute inset-0 h-full w-full" width={size.w} height={size.h} aria-hidden>
      <g transform={transform} fill="none" vectorEffect="non-scaling-stroke">
        {layers.boundaries && <path d={countriesPath} stroke="rgb(var(--c-on-surface-variant))" strokeWidth={1.1} strokeOpacity={0.9} vectorEffect="non-scaling-stroke" />}
        {layers.boundaries && <path d={statesPath} stroke="rgb(var(--c-on-surface-variant))" strokeWidth={0.6} strokeOpacity={0.7} strokeDasharray="3 2" vectorEffect="non-scaling-stroke" />}
        {layers.graticule && <path d={gLines} stroke="rgb(var(--c-outline))" strokeOpacity={0.4} strokeWidth={0.6} strokeDasharray="4 4" vectorEffect="non-scaling-stroke" />}
        {layers.impact && impact?.features.map((f) => {
          const k = f.properties.kind;
          const style = k === "impact" ? { stroke: "rgb(var(--sev-severe))", fill: "rgb(var(--sev-severe) / 0.12)", dash: undefined, w: 1.6 } : k === "risk" ? { stroke: "rgb(var(--sev-moderate))", fill: "rgb(var(--sev-moderate) / 0.06)", dash: "6 3", w: 1.2 } : { stroke: "rgb(var(--c-primary))", fill: "none", dash: "2 3", w: 1.2 };
          return <path key={k} d={geometryToPath(f.geometry)} stroke={style.stroke} fill={style.fill} strokeWidth={style.w} strokeDasharray={style.dash} vectorEffect="non-scaling-stroke" data-testid={`impact-${k}`} />;
        })}
        {layers.envelope && env && <path d={geometryToPath(env.geometry)} fill="rgb(var(--c-tertiary) / 0.06)" stroke="rgb(var(--c-tertiary) / 0.75)" strokeWidth={1} strokeDasharray="3 3" vectorEffect="non-scaling-stroke" data-testid="envelope" />}
        {layers.members && members && <path d={geometryToPath(members.geometry)} stroke="rgb(var(--c-secondary))" strokeOpacity={0.5} strokeWidth={0.9} vectorEffect="non-scaling-stroke" />}
        {layers.track && tracked && <path d={geometryToPath(tracked.geometry)} stroke="rgb(var(--c-on-surface))" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" data-testid="track-line" />}
        {layers.track && extrap && <path d={geometryToPath(extrap.geometry)} stroke="rgb(var(--sev-severe))" strokeWidth={2} strokeDasharray="6 4" strokeLinecap="round" vectorEffect="non-scaling-stroke" data-testid="extrapolation-line" />}
      </g>
      {layers.track && points.map((p) => { const [x, y] = pt(p); const isCur = p.properties.lead_hours === lead; return (
        <g key={p.properties.lead_hours}>
          <circle cx={x} cy={y} r={isCur ? 6 : 3.5} fill={isCur ? "rgb(var(--sev-severe))" : "rgb(var(--c-surface-container-lowest))"} stroke={isCur ? "rgb(var(--c-surface-container-lowest))" : "rgb(var(--c-on-surface))"} strokeWidth={isCur ? 2 : 1.6} />
          {isCur && <circle cx={x} cy={y} r={13} fill="none" stroke="rgb(var(--sev-severe))" strokeWidth={1.2} strokeDasharray="2 2" />}
        </g>); })}
      {layers.track && exPoints.map((p) => { const [x, y] = pt(p); return <circle key={p.properties.lead_hours} cx={x} cy={y} r={3.5} fill="none" stroke="rgb(var(--sev-severe))" strokeWidth={1.5} />; })}
      {layers.track && cur && (() => { const [x, y] = pt(cur); return (
        <g transform={`translate(${x + 16} ${y - 18})`}>
          <rect width={132} height={30} rx={3} fill="rgb(var(--c-surface-container-lowest))" stroke="rgb(var(--c-on-surface))" strokeWidth={0.8} />
          <text x={6} y={12} fontSize={10} fontWeight={700} className="fill-error font-mono">{leadLabel(lead)} · SYNTHETIC EVENT</text>
          <text x={6} y={24} fontSize={9} className="fill-on-surface font-mono">{cur.properties.max_intensity?.toFixed(0)} mm/6h · {cur.properties.speed_kmh?.toFixed(0)} km/h</text>
        </g>); })()}
      {arrows}
      {view.zoom > 26 && layers.boundaries && labels.map((l) => { const [x, y] = project(view, size, l.c[0], l.c[1]); if (x < 0 || y < 0 || x > size.w || y > size.h) return null; return <text key={l.name} x={x} y={y} textAnchor="middle" fontSize={10} className="fill-on-surface-variant font-medium" stroke="rgb(var(--c-surface-container-lowest))" strokeWidth={3} paintOrder="stroke" opacity={0.85}>{l.name}</text>; })}
      {layers.graticule && lats.map((y) => <text key={`la${y}`} x={5} y={project(view, size, view.lon, y)[1] - 2} fontSize={9} className="fill-on-surface-variant font-mono" stroke="rgb(var(--c-surface-container-lowest))" strokeWidth={2.5} paintOrder="stroke">{Math.abs(y)}°{y >= 0 ? "N" : "S"}</text>)}
      {layers.graticule && lons.map((x) => <text key={`lo${x}`} x={project(view, size, x, view.lat)[0] + 3} y={size.h - 6} fontSize={9} className="fill-on-surface-variant font-mono" stroke="rgb(var(--c-surface-container-lowest))" strokeWidth={2.5} paintOrder="stroke">{Math.abs(x)}°{x >= 0 ? "E" : "W"}</text>)}
      {measure.map(([lon, lat], i) => { const [x, y] = project(view, size, lon, lat); return <circle key={i} cx={x} cy={y} r={4} fill="rgb(var(--c-primary))" stroke="white" strokeWidth={1.5} />; })}
      {measure.length === 2 && (() => { const a = project(view, size, ...measure[0]!), b = project(view, size, ...measure[1]!); return <line x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} stroke="rgb(var(--c-primary))" strokeWidth={2} strokeDasharray="5 3" />; })()}
      {probe && (() => { const [x, y] = project(view, size, probe[0], probe[1]); return <g><circle cx={x} cy={y} r={6} fill="none" stroke="rgb(var(--c-primary))" strokeWidth={2} /><path d={`M${x - 10} ${y}H${x + 10}M${x} ${y - 10}V${y + 10}`} stroke="rgb(var(--c-primary))" strokeWidth={1.2} /></g>; })()}
    </svg>
  );
}
