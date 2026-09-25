import { formatIst, formatUser, formatUtc, IST } from "@/lib/time";
import { useUi } from "@/stores/ui";

/** Always shows UTC and IST (each labelled) and, when different, the user's selected zone. Never converts silently. */
export function TimeStamp({ iso, compact = false }: { iso: string; compact?: boolean }): JSX.Element {
  const tz = useUi((s) => s.timeZone);
  const extra = tz !== "UTC" && tz !== IST ? formatUser(iso, tz) : null;
  return (
    <time dateTime={iso} className="font-mono text-label-num-md">
      <span className="font-semibold">{formatUtc(iso)}</span>
      {!compact && <span className="text-on-surface-variant"> · {formatIst(iso)}</span>}
      {!compact && extra && <span className="text-on-surface-variant"> · {extra}</span>}
    </time>
  );
}
