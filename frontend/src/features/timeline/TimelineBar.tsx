import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, Pause, Play } from "lucide-react";
import { useEffect } from "react";

import { ControlButton } from "@/components/ControlButton";
import { formatIst, formatUtc, leadLabel, shortDayHour } from "@/lib/time";
import { cn } from "@/lib/utils";
import { useTimeline } from "@/stores/timeline";

interface Props {
  validTimes: string[];
  peakLead?: number;
  extrapolationHours: number[];
}

/** Forecast time machine: play/pause/step and direct lead selection. Drives the map, panels and alert region. */
export function TimelineBar({ validTimes, peakLead, extrapolationHours }: Props): JSX.Element {
  const { leads, index, playing, speed, toggle, step, first, setLead, setSpeed, pause } = useTimeline();
  useEffect(() => {
    if (!playing) return;
    const t = window.setInterval(() => {
      const s = useTimeline.getState();
      if (s.index >= s.leads.length - 1) s.pause();
      else s.step(1);
    }, 1100 / speed);
    return () => window.clearInterval(t);
  }, [playing, speed]);

  const cur = leads[index];
  const curTime = validTimes[index];
  return (
    <section aria-label="Forecast time machine" className="border-t border-outline-variant/50 bg-surface-container-lowest p-2">
      <div className="flex flex-wrap items-center justify-between gap-2 px-1 pb-1.5">
        <div className="flex items-center gap-1" role="group" aria-label="Playback controls">
          <ControlButton label="First lead time" icon={ChevronsLeft} size="sm" tooltip="First lead time" onClick={() => { pause(); first(); }} disabled={index === 0} disabledReason="Already at the first lead time" />
          <ControlButton label="Step back" icon={ChevronLeft} size="sm" tooltip="Step back one lead time" onClick={() => { pause(); step(-1); }} disabled={index === 0} disabledReason="Already at the first lead time" />
          <ControlButton label={playing ? "Pause forecast" : "Play forecast"} icon={playing ? Pause : Play} variant="solid" size="sm" tooltip={playing ? "Pause" : "Play through lead times"} onClick={toggle}>{playing ? "PAUSE" : "PLAY FORECAST"}</ControlButton>
          <ControlButton label="Step forward" icon={ChevronRight} size="sm" tooltip="Step forward one lead time" onClick={() => { pause(); step(1); }} disabled={index >= leads.length - 1} disabledReason="Already at the last lead time" />
          <ControlButton label="Last lead time" icon={ChevronsRight} size="sm" tooltip="Last lead time" onClick={() => { pause(); useTimeline.getState().last(); }} disabled={index >= leads.length - 1} disabledReason="Already at the last lead time" />
          <div className="mx-1 h-4 w-px bg-outline-variant" aria-hidden />
          <div className="flex rounded bg-surface-container-low p-0.5" role="group" aria-label="Playback speed">
            {([1, 2, 4] as const).map((s) => (
              <button key={s} type="button" aria-pressed={speed === s} onClick={() => setSpeed(s)} className={cn("rounded px-1.5 py-[1px] font-mono text-label-num-sm", speed === s ? "bg-surface-container-lowest font-bold text-primary shadow-sm" : "text-on-surface-variant hover:text-on-surface")}>{s}x</button>
            ))}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3 font-mono text-label-num-md" aria-live="polite">
          <span className="text-on-surface-variant">VALID TIME</span>
          {cur !== undefined && curTime && <span className="rounded bg-primary/10 px-1.5 font-bold text-primary" data-testid="valid-time">{leadLabel(cur)} · {formatUtc(curTime)} · {formatIst(curTime)}</span>}
        </div>
      </div>
      <label className="sr-only" htmlFor="lead-slider">Forecast lead time</label>
      <input id="lead-slider" type="range" min={0} max={Math.max(0, leads.length - 1)} step={1} value={index} onChange={(e) => { pause(); const l = leads[Number(e.target.value)]; if (l !== undefined) setLead(l); }} aria-valuetext={cur !== undefined && curTime ? `${leadLabel(cur)}, ${formatUtc(curTime)}` : undefined} className="mb-1.5 w-full accent-[rgb(var(--c-primary))]" />
      <div className="flex gap-1 overflow-x-auto rounded bg-surface-container-low p-1" role="group" aria-label="Lead times">
        {leads.map((l, i) => {
          const active = i === index;
          const vt = validTimes[i];
          return (
            <button key={l} type="button" aria-pressed={active} aria-label={`${leadLabel(l)}${l === peakLead ? " (peak intensity)" : ""}${vt ? `, ${formatUtc(vt)}` : ""}`} onClick={() => { pause(); setLead(l); }}
              className={cn("flex min-w-[68px] flex-1 flex-col items-center justify-center rounded px-1 py-1 transition-colors", active ? "bg-primary text-on-primary shadow-sm" : "bg-surface-container-lowest text-on-surface-variant hover:bg-surface-container", l === peakLead && !active && "ring-1 ring-error")}>
              <span className="font-mono text-label-num-md font-bold">{l === peakLead ? "★ " : ""}{leadLabel(l)}</span>
              <span className="font-mono text-[9px] opacity-90">{vt ? shortDayHour(vt) : ""}</span>
            </button>
          );
        })}
      </div>
      <p className="px-1 pt-1 text-body-xs text-on-surface-variant">
        ★ = peak intensity. Times are UTC unless labelled. {extrapolationHours.length > 0 && <>Dashed track beyond T+{leads[leads.length - 1]} is a constant-velocity <b>extrapolation</b> (+{extrapolationHours.join(", +")} h), not part of the forecast data.</>}
      </p>
    </section>
  );
}
