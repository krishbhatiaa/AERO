import type { Geometry, Position } from "@/types/api";

const R_KM = 6371.0088;
const rad = (d: number): number => (d * Math.PI) / 180;

export function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const dphi = rad(lat2 - lat1);
  const dl = rad(lon2 - lon1);
  const a = Math.sin(dphi / 2) ** 2 + Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(dl / 2) ** 2;
  return 2 * R_KM * Math.asin(Math.min(1, Math.sqrt(a)));
}

/** Viewport of the equirectangular map: centre (lon/lat), zoom = screen pixels per degree of latitude. */
export interface View {
  lon: number;
  lat: number;
  zoom: number;
}
export interface Size {
  w: number;
  h: number;
}
export const STANDARD_PARALLEL = 18;
const kx = (v: View): number => v.zoom * Math.cos(rad(STANDARD_PARALLEL));

export function project(v: View, s: Size, lon: number, lat: number): [number, number] {
  return [s.w / 2 + (lon - v.lon) * kx(v), s.h / 2 - (lat - v.lat) * v.zoom];
}
export function unproject(v: View, s: Size, x: number, y: number): [number, number] {
  return [v.lon + (x - s.w / 2) / kx(v), v.lat - (y - s.h / 2) / v.zoom];
}
/** SVG transform that maps raw lon/lat path coordinates to screen pixels (paths stay in data space). */
export function dataToScreenTransform(v: View, s: Size): string {
  const sx = kx(v);
  const tx = s.w / 2 - v.lon * sx;
  const ty = s.h / 2 + v.lat * v.zoom;
  return `translate(${tx} ${ty}) scale(${sx} ${-v.zoom})`;
}

export function fitView(bounds: [number, number, number, number], s: Size, padding = 0.94): View {
  const [w, so, e, n] = bounds;
  const zoom = Math.min((s.w * padding) / ((e - w) * Math.cos(rad(STANDARD_PARALLEL))), (s.h * padding) / (n - so));
  return { lon: (w + e) / 2, lat: (so + n) / 2, zoom: Math.max(zoom, 1) };
}
export function zoomAt(v: View, s: Size, x: number, y: number, factor: number, min = 6, max = 400): View {
  const [lon, lat] = unproject(v, s, x, y);
  const zoom = Math.min(max, Math.max(min, v.zoom * factor));
  const next = { ...v, zoom };
  const [lon2, lat2] = unproject(next, s, x, y);
  return { zoom, lon: v.lon + (lon - lon2), lat: v.lat + (lat - lat2) };
}
export function panBy(v: View, dx: number, dy: number): View {
  return { ...v, lon: v.lon - dx / kx(v), lat: v.lat + dy / v.zoom };
}

function ring(coords: Position[]): string {
  return coords.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(4)} ${y.toFixed(4)}`).join("") + "Z";
}
/** SVG path (in lon/lat data space) for a GeoJSON geometry. Points return an empty string. */
export function geometryToPath(g: Geometry): string {
  switch (g.type) {
    case "LineString":
      return g.coordinates.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(4)} ${y.toFixed(4)}`).join("");
    case "MultiLineString":
      return g.coordinates.map((l) => l.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(4)} ${y.toFixed(4)}`).join("")).join("");
    case "Polygon":
      return g.coordinates.map(ring).join("");
    case "MultiPolygon":
      return g.coordinates.map((p) => p.map(ring).join("")).join("");
    default:
      return "";
  }
}

export function formatLat(lat: number): string {
  return `${Math.abs(lat).toFixed(2)}°${lat >= 0 ? "N" : "S"}`;
}
export function formatLon(lon: number): string {
  return `${Math.abs(lon).toFixed(2)}°${lon >= 0 ? "E" : "W"}`;
}

export function normalizeLon(lon: number): number {
  let l = lon % 360;
  if (l > 180) l -= 360;
  if (l < -180) l += 360;
  return l;
}

export function wrapForView(lon: number, viewLon: number): number {
  let l = lon;
  while (l - viewLon > 180) l -= 360;
  while (l - viewLon < -180) l += 360;
  return l;
}

function isAntimeridianCrossing(coords: [number, number][]): boolean {
  for (let i = 1; i < coords.length; i++) {
    const dx = Math.abs(coords[i]![0] - coords[i - 1]![0]);
    if (dx > 180) return true;
  }
  return false;
}

function splitRing(coords: [number, number][]): [number, number][][] {
  if (!isAntimeridianCrossing(coords)) return [coords];
  const segments: [number, number][][] = [];
  let current: [number, number][] = [coords[0]!];
  for (let i = 1; i < coords.length; i++) {
    const prev = coords[i - 1]!;
    const cur = coords[i]!;
    const dx = cur[0] - prev[0];
    if (Math.abs(dx) > 180) {
      const crossLon = dx > 0 ? 180 : -180;
      const lat = prev[1] + (cur[1] - prev[1]) * ((crossLon - prev[0]) / (cur[0] - prev[0]));
      current.push([crossLon, lat]);
      segments.push(current);
      current = [[-crossLon, lat], cur];
    } else {
      current.push(cur);
    }
  }
  segments.push(current);
  return segments;
}

export function splitAtAntimeridian(feature: { type: string; geometry: { type: string; coordinates: unknown } }): { type: string; geometry: { type: string; coordinates: unknown } }[] {
  const { geometry } = feature;
  if (geometry.type === "Polygon") {
    const rings = geometry.coordinates as [number, number][][];
    const splitRings = rings.flatMap(splitRing);
    const west: [number, number][][] = [];
    const east: [number, number][][] = [];
    for (const ring of splitRings) {
      const avgLon = ring.reduce((s, c) => s + c[0], 0) / ring.length;
      if (avgLon < 0) west.push(ring);
      else east.push(ring);
    }
    const result: { type: string; geometry: { type: string; coordinates: unknown } }[] = [];
    if (west.length > 0) result.push({ type: "Feature", geometry: { type: "Polygon", coordinates: west } });
    if (east.length > 0) result.push({ type: "Feature", geometry: { type: "Polygon", coordinates: east } });
    return result.length > 0 ? result : [{ type: "Feature", geometry }];
  }
  if (geometry.type === "MultiPolygon") {
    const polys = geometry.coordinates as [number, number][][][];
    const allSplit = polys.flatMap((poly) => {
      const splitRings = poly.flatMap(splitRing);
      const west: [number, number][][] = [];
      const east: [number, number][][] = [];
      for (const ring of splitRings) {
        const avgLon = ring.reduce((s, c) => s + c[0], 0) / ring.length;
        if (avgLon < 0) west.push(ring);
        else east.push(ring);
      }
      const result: [number, number][][][] = [];
      if (west.length > 0) result.push(west);
      if (east.length > 0) result.push(east);
      return result.length > 0 ? result : [poly];
    });
    return [{ type: "Feature", geometry: { type: "MultiPolygon", coordinates: allSplit } }];
  }
  return [{ type: "Feature", geometry }];
}
