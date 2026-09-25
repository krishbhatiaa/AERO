/** Colour ramps for map rasters. Precipitation bins follow the workstation mockup, re-scaled to mm per 6 h. */
export type RGBA = [number, number, number, number];

export interface Stop {
  min: number;
  label: string;
  color: RGBA;
}

export const PRECIP_STOPS: Stop[] = [
  { min: 1, label: "1", color: [187, 247, 208, 200] },
  { min: 5, label: "5", color: [74, 222, 128, 215] },
  { min: 15, label: "15", color: [250, 204, 21, 225] },
  { min: 30, label: "30", color: [251, 146, 60, 235] },
  { min: 60, label: "60", color: [239, 68, 68, 240] },
  { min: 100, label: "100", color: [153, 27, 27, 245] },
  { min: 150, label: ">150", color: [88, 28, 135, 250] },
];

export const ANOMALY_STOPS: Stop[] = [
  { min: 0.95, label: "P95", color: [250, 204, 21, 170] },
  { min: 0.99, label: "P99", color: [249, 115, 22, 210] },
  { min: 0.999, label: "P99.9", color: [220, 38, 38, 235] },
];

export function rampColor(stops: Stop[], v: number): RGBA | null {
  if (!Number.isFinite(v) || v < (stops[0]?.min ?? Infinity)) return null;
  let hit = stops[0];
  for (const s of stops) if (v >= s.min) hit = s;
  return hit ? hit.color : null;
}

/** Colourise a float grid (south-to-north rows) into top-down RGBA bytes for a canvas ImageData. */
export function colorizeToRGBA(values: Float32Array, nx: number, ny: number, stops: Stop[]): Uint8ClampedArray {
  const out = new Uint8ClampedArray(nx * ny * 4);
  for (let row = 0; row < ny; row++) {
    const srcRow = ny - 1 - row; // flip: canvas row 0 is north
    for (let col = 0; col < nx; col++) {
      const c = rampColor(stops, values[srcRow * nx + col] ?? NaN);
      if (c) out.set(c, (row * nx + col) * 4);
    }
  }
  return out;
}
