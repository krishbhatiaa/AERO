import type { FieldPayload } from "@/types/api";

export interface DecodedField {
  payload: FieldPayload;
  values: Float32Array;
  nx: number;
  ny: number;
}

/** Decode the API's little-endian float32/base64 raster. Throws on inconsistent shape. */
export function decodeField(p: FieldPayload): DecodedField {
  const bin = atob(p.values_b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  const [ny, nx] = p.shape;
  if (bytes.byteLength !== nx * ny * 4) throw new RangeError(`Field payload has ${bytes.byteLength} bytes, expected ${nx * ny * 4}`);
  const values = new Float32Array(bytes.buffer, bytes.byteOffset, nx * ny);
  return { payload: p, values, nx, ny };
}

/** Value at (lon, lat) or null outside the grid. Rows run south to north. */
export function sampleField(f: DecodedField, lon: number, lat: number): number | null {
  const [w, s, e, n] = f.payload.bounds;
  if (lon < w || lon >= e || lat < s || lat >= n) return null;
  const col = Math.min(f.nx - 1, Math.floor(((lon - w) / (e - w)) * f.nx));
  const row = Math.min(f.ny - 1, Math.floor(((lat - s) / (n - s)) * f.ny));
  return f.values[row * f.nx + col] ?? null;
}
