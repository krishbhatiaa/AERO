import { ArrowRight, Cpu, FlaskConical, Gauge, Layers, Network, Scale } from "lucide-react";
import { Link } from "react-router-dom";

import { AsyncBoundary } from "@/components/AsyncBoundary";
import { PipelineDiagram } from "@/features/PipelineDiagram";
import { useCapabilities, useDownscalingEval, useTrackingEval } from "@/hooks/queries";
import { fmt } from "@/lib/utils";

/** Decorative vortex + graph illustration (explicitly not model output). */
function HeroGraphic(): JSX.Element {
  const nodes = Array.from({ length: 34 }, (_, i) => {
    const a = i * 2.399963, r = 26 + Math.sqrt(i) * 44;
    return { x: 600 + r * Math.cos(a) * 1.55, y: 320 + r * Math.sin(a) * 0.95 };
  });
  return (
    <svg viewBox="0 0 1200 640" className="h-full w-full" aria-hidden fill="none">
      <defs><radialGradient id="glow" cx="50%" cy="50%" r="50%"><stop offset="0" stopColor="rgb(var(--c-primary))" stopOpacity="0.35" /><stop offset="1" stopColor="rgb(var(--c-primary))" stopOpacity="0" /></radialGradient></defs>
      <circle cx="600" cy="320" r="300" fill="url(#glow)" />
      {[300, 230, 160, 95].map((r, i) => <ellipse key={r} cx="600" cy="320" rx={r * 1.5} ry={r * 0.95} stroke="rgb(var(--c-primary))" strokeOpacity={0.18 + i * 0.12} strokeWidth="1.4" strokeDasharray={i === 0 ? "4 5" : undefined} />)}
      <path d="M420 370C490 430 590 410 640 350C680 300 660 240 600 230C530 220 480 270 510 320C530 350 580 360 600 330" stroke="rgb(var(--c-primary))" strokeWidth="3" strokeLinecap="round" />
      <path d="M380 400C450 500 690 500 780 380C850 270 780 130 600 110" stroke="rgb(var(--c-secondary))" strokeWidth="1.8" strokeDasharray="6 5" strokeLinecap="round" />
      <g stroke="rgb(var(--c-primary))" strokeOpacity="0.28" strokeWidth="1">{nodes.map((n, i) => { const m = nodes[(i * 7 + 3) % nodes.length]!; const o = nodes[(i * 5 + 1) % nodes.length]!; return <g key={i}><line x1={n.x} y1={n.y} x2={m.x} y2={m.y} /><line x1={n.x} y1={n.y} x2={o.x} y2={o.y} /></g>; })}</g>
      {nodes.map((n, i) => <circle key={i} cx={n.x} cy={n.y} r={i % 9 === 0 ? 5 : 3.2} fill={i === 0 ? "rgb(var(--c-error))" : "rgb(var(--c-primary))"} />)}
    </svg>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub: string }): JSX.Element {
  return <div className="rounded-lg bg-surface-container-low p-4"><div className="text-label-header uppercase text-on-surface-variant">{label}</div><div className="mt-1 font-mono text-[26px] font-semibold leading-8 text-primary">{value}</div><div className="mt-1 text-body-xs text-on-surface-variant">{sub}</div></div>;
}

export function Platform(): JSX.Element {
  const caps = useCapabilities();
  const ds = useDownscalingEval();
  const tr = useTrackingEval();
  const best = ds.data?.methods.find((m) => m.method === "bicubic_conservative");
  const nearest = ds.data?.methods.find((m) => m.method === "nearest");
  return (
    <div data-theme="dark" className="min-h-full bg-background text-on-surface" data-testid="platform-page">
      <section className="relative overflow-hidden px-6 pb-16 pt-14">
        <div className="pointer-events-none absolute -top-40 left-1/2 h-[520px] w-[980px] -translate-x-1/2 bg-gradient-to-b from-primary/15 to-transparent blur-[140px]" aria-hidden />
        <div className="relative mx-auto flex max-w-6xl flex-col items-center text-center">
          <span className="mb-4 inline-flex items-center gap-2 rounded-full bg-surface-container-high px-3 py-1 text-label-header uppercase tracking-widest text-primary"><span className="h-2 w-2 animate-pulseDot rounded-full bg-primary" aria-hidden />PS 26078 · MoES / NCMRWF · research prototype</span>
          <h1 className="max-w-4xl text-[40px] font-bold leading-[46px] tracking-tight sm:text-[60px] sm:leading-[64px]">Extreme weather, tracked and <span className="bg-gradient-to-r from-on-surface via-primary to-primary-fixed bg-clip-text text-transparent">measured honestly.</span></h1>
          <p className="mt-5 max-w-3xl text-[15px] leading-6 text-on-surface-variant">Anomaly detection → event tracking → 12 km-class to 5 km-class downscaling → physics checks → uncertainty → risk → localized alerts. Every stage ships with a classical baseline; a learned model is promoted only when it beats that baseline on held-out data. Every number on this page comes from the running backend.</p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Link to="/" className="inline-flex items-center gap-2 rounded-full bg-primary-container px-6 py-3 font-mono text-[13px] font-semibold text-on-primary-container shadow-[0_0_24px_rgba(6,182,212,0.3)] hover:bg-primary">Launch workstation <ArrowRight aria-hidden className="h-4 w-4" /></Link>
            <Link to="/models" className="inline-flex items-center gap-2 rounded-full bg-surface-container-high px-6 py-3 font-mono text-[13px] hover:bg-surface-container-highest"><Layers aria-hidden className="h-4 w-4 text-primary" />See pipeline status</Link>
          </div>
          <div className="mt-10 aspect-[16/7] w-full max-w-5xl overflow-hidden rounded-xl bg-surface-container-lowest p-2 shadow-2xl"><div className="grid-bg relative h-full w-full rounded-lg bg-surface-container-low"><HeroGraphic /><span className="absolute bottom-2 left-3 rounded bg-surface-container-lowest/80 px-2 py-0.5 font-mono text-label-num-sm text-on-surface-variant">Illustrative graphic (spherical mesh + vortex) — not model output</span></div></div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-6 py-10" aria-labelledby="measured">
        <span className="text-label-header uppercase tracking-widest text-primary">Measured on the synthetic scenario</span>
        <h2 id="measured" className="mt-1 max-w-3xl text-[26px] font-bold leading-8">What interpolation loses — the gap a learned downscaler would have to close.</h2>
        <p className="mt-2 max-w-3xl text-body-md text-on-surface-variant">These are baseline results against the scenario generator's own fine-grid truth. They show <i>that</i> extremes get smoothed, not real-world skill. No learned model has been trained.</p>
        <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <AsyncBoundary query={ds} label="evaluation" className="contents" skeleton={<div className="skeleton h-28 w-full" />}>
            {() => (<>
              <Stat label="Peak error · nearest" value={`${fmt(nearest?.metrics.peak_error?.mean, 0)} mm`} sub="6-h peak vs truth (negative = underestimated)" />
              <Stat label="Peak error · bicubic + conservation" value={`${fmt(best?.metrics.peak_error?.mean, 0)} mm`} sub="best interpolation baseline on this scenario" />
              <Stat label="Fine-scale variance recovered" value={fmt(best?.metrics.psd_ratio_band?.mean, 2)} sub="PSD ratio at 12–40 km wavelengths (1 = full)" />
            </>)}
          </AsyncBoundary>
          <AsyncBoundary query={tr} label="tracking evaluation" className="contents" skeleton={<div className="skeleton h-28 w-full" />}>
            {(t) => <Stat label="Kalman vs persistence · 1 step" value={`${fmt(t.hindcast.kalman_km["1"], 0)} vs ${fmt(t.hindcast.persistence_km["1"], 0)} km`} sub={`centroid error at +6 h (n=${t.hindcast.n_samples["1"] ?? "?"}); mechanics check only`} />}
          </AsyncBoundary>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-6 py-10" aria-labelledby="pipeline">
        <span className="text-label-header uppercase tracking-widest text-primary">Architecture</span>
        <h2 id="pipeline" className="mt-1 text-[26px] font-bold leading-8">Baseline first, learned second — with status you can verify.</h2>
        <div className="mt-6"><AsyncBoundary query={caps} label="capabilities">{(c) => <PipelineDiagram caps={c} />}</AsyncBoundary></div>
      </section>

      <section className="mx-auto grid max-w-6xl gap-3 px-6 pb-16 md:grid-cols-2 lg:grid-cols-4" aria-label="Principles">
        {[
          { Icon: FlaskConical, t: "Scientific honesty", d: "Every layer is labelled OBSERVED, REANALYSIS, FORECAST, MODEL PREDICTION or SYNTHETIC. Derived products inherit the weakest label." },
          { Icon: Scale, t: "Baselines must be beaten", d: "Learned models are promoted only after beating a named baseline on held-out data with bootstrap confidence intervals." },
          { Icon: Network, t: "Uncertainty is a feature", d: "Ensemble spread, position envelopes and confidence classes are shown next to every prediction." },
          { Icon: Gauge, t: "Decision support, not warnings", d: "Risk categories are configurable analytical labels. Official warnings come from IMD and the disaster management authorities." },
        ].map(({ Icon, t, d }) => <div key={t} className="rounded-xl bg-surface-container-low p-5"><Icon aria-hidden className="mb-3 h-6 w-6 text-primary" /><h3 className="text-head-md">{t}</h3><p className="mt-1 text-body-sm text-on-surface-variant">{d}</p></div>)}
      </section>
      <footer className="border-t border-outline-variant/40 px-6 py-6 text-center text-body-xs text-on-surface-variant"><Cpu aria-hidden className="mr-1 inline h-3.5 w-3.5" />Research prototype prepared for PS 26078 (MoES / NCMRWF). Not an official product of any government body. Boundaries: Natural Earth (public domain), not official.</footer>
    </div>
  );
}
