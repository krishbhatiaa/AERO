export function cn(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}
export const fmt = (v: number | null | undefined, digits = 1): string => (v === null || v === undefined || Number.isNaN(v) ? "—" : v.toFixed(digits));
export const fmtInt = (v: number | null | undefined): string => (v === null || v === undefined ? "—" : Math.round(v).toLocaleString("en-US"));
export const pct = (v: number | null | undefined, digits = 0): string => (v === null || v === undefined ? "—" : `${(v * 100).toFixed(digits)}%`);
export function clamp(v: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, v));
}
export function bearingToCompass(deg: number): string {
  const names = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];
  return names[Math.round((((deg % 360) + 360) % 360) / 22.5) % 16] ?? "N";
}
