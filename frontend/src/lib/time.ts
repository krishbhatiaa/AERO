/**
 * Time handling. The backend speaks UTC only; conversion happens here and every displayed instant is labelled
 * with its zone. There are no silent conversions: callers always choose the zone explicitly.
 */
export const IST = "Asia/Kolkata";

function parts(iso: string, timeZone: string): Record<string, string> {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) throw new RangeError(`Invalid timestamp: ${iso}`);
  const f = new Intl.DateTimeFormat("en-GB", { timeZone, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
  return Object.fromEntries(f.formatToParts(d).map((p) => [p.type, p.value]));
}

export function formatIn(iso: string, timeZone: string, label: string): string {
  const p = parts(iso, timeZone);
  return `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute} ${label}`;
}
export const formatUtc = (iso: string): string => formatIn(iso, "UTC", "UTC");
export const formatIst = (iso: string): string => formatIn(iso, IST, "IST");

export function zoneLabel(timeZone: string, at: Date = new Date()): string {
  if (timeZone === "UTC") return "UTC";
  if (timeZone === IST) return "IST";
  const name = new Intl.DateTimeFormat("en-GB", { timeZone, timeZoneName: "short" }).formatToParts(at).find((p) => p.type === "timeZoneName")?.value;
  return name ?? timeZone;
}
export const formatUser = (iso: string, timeZone: string): string => formatIn(iso, timeZone, zoneLabel(timeZone, new Date(iso)));

export function shortDayHour(iso: string, timeZone = "UTC"): string {
  const p = parts(iso, timeZone);
  return `${p.day}/${p.hour}${timeZone === "UTC" ? "Z" : ""}`;
}

/** "T+06" style lead label. */
export const leadLabel = (h: number): string => `T+${String(h).padStart(2, "0")}`;

export function isKnownTimeZone(tz: string): boolean {
  try {
    new Intl.DateTimeFormat("en-GB", { timeZone: tz });
    return true;
  } catch {
    return false;
  }
}
