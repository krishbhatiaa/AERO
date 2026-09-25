import { CheckCircle2, CircleAlert, CircleOff, Play } from "lucide-react";
import { useState } from "react";

import { AsyncBoundary } from "@/components/AsyncBoundary";
import { ControlButton } from "@/components/ControlButton";
import { KV, Panel } from "@/components/Panel";
import { StatusChip } from "@/components/StatusChip";
import { TimeStamp } from "@/components/TimeStamp";
import { useLive } from "@/hooks/live";
import { useCapabilities, useHealth, useJobs, useReady, useRunPipeline } from "@/hooks/queries";
import { ApiClientError } from "@/lib/api";
import { pct } from "@/lib/utils";
import type { CapabilityStatus } from "@/types/api";

const ORDER: CapabilityStatus[] = ["IMPLEMENTED", "PARTIALLY_IMPLEMENTED", "REQUIRES_REAL_DATA", "REQUIRES_GPU_TRAINING", "RESEARCH_EXTENSION"];

function DepIcon({ status }: { status: string }): JSX.Element {
  if (status === "ok") return <CheckCircle2 aria-hidden className="h-4 w-4 text-primary" />;
  if (status === "not_configured") return <CircleOff aria-hidden className="h-4 w-4 text-on-surface-variant" />;
  return <CircleAlert aria-hidden className="h-4 w-4 text-error" />;
}

export function System(): JSX.Element {
  const health = useHealth();
  const ready = useReady();
  const caps = useCapabilities();
  const jobs = useJobs();
  const run = useRunPipeline();
  const ws = useLive((s) => s.status);
  const progress = useLive((s) => s.jobProgress);
  const [seed, setSeed] = useState(7);
  const [members, setMembers] = useState(10);
  const invalid = !Number.isInteger(seed) || seed < 0 || seed > 1_000_000 || !Number.isInteger(members) || members < 2 || members > 30;
  const err = run.error instanceof ApiClientError ? run.error : null;
  return (
    <div className="mx-auto max-w-6xl space-y-4 p-4">
      <div><h1 className="text-head-lg">System</h1><p className="text-body-sm text-on-surface-variant">Health, dependencies, capability status and pipeline jobs.</p></div>
      <div className="grid gap-3 lg:grid-cols-2">
        <Panel title="Service health">
          <AsyncBoundary query={health} label="health">{(h) => (
            <><dl><KV k="Status" v={h.status.toUpperCase()} /><KV k="Version" v={h.version} /><KV k="Uptime" v={`${Math.round(h.uptime_s)} s`} /><KV k="Environment" v={h.mode.env} /><KV k="Auth mode" v={h.mode.auth_mode} /><KV k="Demo mode" v={String(h.mode.demo_mode)} /><KV k="REAL_DATA_MODE" v={String(h.mode.real_data_mode)} /><KV k="Data in use" v={h.mode.data_kind_in_use} /><KV k="Live channel" v={ws.toUpperCase()} /></dl>{h.mode.note && <p className="pt-1 text-body-xs text-on-surface-variant">{h.mode.note}</p>}</>)}</AsyncBoundary>
        </Panel>
        <Panel title="Dependencies (readiness)">
          <AsyncBoundary query={ready} label="readiness">{(r) => (
            <ul className="space-y-1.5">{Object.entries(r.dependencies).map(([name, d]) => (
              <li key={name} className="flex items-start gap-2"><DepIcon status={d.status} /><div><div className="font-mono text-label-num-md font-semibold">{name} <span className="font-normal text-on-surface-variant">— {d.status.replace("_", " ")}</span></div>{d.detail && <div className="text-body-xs text-on-surface-variant">{d.detail}</div>}</div></li>))}</ul>)}</AsyncBoundary>
        </Panel>
      </div>
      <Panel title="Run the pipeline on a synthetic scenario">
        <form className="flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); if (!invalid) run.mutate({ scenario_seed: seed, n_members: members }); }}>
          <div><label htmlFor="seed" className="block text-label-header uppercase text-on-surface-variant">Scenario seed (0–1,000,000)</label><input id="seed" type="number" value={seed} min={0} max={1000000} onChange={(e) => setSeed(Number(e.target.value))} aria-invalid={invalid} className="mt-0.5 w-32 rounded border border-outline-variant bg-surface-container-lowest px-2 py-1 font-mono text-label-num-md" /></div>
          <div><label htmlFor="members" className="block text-label-header uppercase text-on-surface-variant">Ensemble members (2–30)</label><input id="members" type="number" value={members} min={2} max={30} onChange={(e) => setMembers(Number(e.target.value))} aria-invalid={invalid} className="mt-0.5 w-32 rounded border border-outline-variant bg-surface-container-lowest px-2 py-1 font-mono text-label-num-md" /></div>
          <ControlButton label="Run pipeline" icon={Play} variant="solid" loading={run.isPending} disabled={invalid} disabledReason="Seed must be 0–1,000,000 and members 2–30" tooltip="Asynchronous job; progress streams over the WebSocket">Run pipeline</ControlButton>
        </form>
        {err && <div role="alert" className="mt-2 text-body-sm text-error">{err.problem?.detail || err.message}{err.status === 401 || err.status === 403 ? " Set an API key with sufficient role in the header." : ""}</div>}
        <AsyncBoundary query={jobs} label="jobs" isEmpty={(d) => d.length === 0} emptyText="No jobs yet." className="mt-3">
          {(rows) => (
            <ul className="space-y-1.5" aria-label="Jobs">{rows.slice(0, 8).map((j) => { const live = progress[j.id]; const frac = j.status === "SUCCEEDED" ? 1 : live?.fraction ?? j.progress; return (
              <li key={j.id} className="rounded border border-outline-variant/50 p-2">
                <div className="flex flex-wrap items-center justify-between gap-2"><span className="font-mono text-label-num-md">{j.type} · {j.id.slice(0, 8)}</span><span className="font-mono text-label-num-md font-semibold">{j.status}</span></div>
                <div className="mt-1 h-1.5 overflow-hidden rounded bg-surface-container" role="progressbar" aria-label={`Job ${j.id.slice(0, 8)} progress`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(frac * 100)}><div className="h-full bg-primary transition-[width] duration-300" style={{ width: pct(frac) }} /></div>
                <div className="mt-1 flex justify-between text-body-xs text-on-surface-variant"><span>{live?.step ?? j.current_step ?? "queued"}</span><TimeStamp iso={j.created_at} compact /></div>
                {j.error && <div className="text-body-xs text-error">{j.error}</div>}
              </li>); })}</ul>)}
        </AsyncBoundary>
      </Panel>
      <Panel title="Capability status (what exists vs what is planned)">
        <AsyncBoundary query={caps} label="capabilities">{(c) => (
          <div className="space-y-3">{ORDER.map((st) => { const rows = c.capabilities.filter((x) => x.status === st); if (!rows.length) return null; return (
            <section key={st} aria-label={st}><div className="mb-1 flex items-center gap-2"><StatusChip status={st} /><span className="font-mono text-label-num-sm text-on-surface-variant">{rows.length}</span></div>
              <ul className="grid gap-x-6 gap-y-1 md:grid-cols-2">{rows.map((r) => <li key={r.id} className="text-body-sm"><b>{r.name}</b><span className="text-on-surface-variant"> — {r.detail}</span></li>)}</ul></section>); })}</div>)}</AsyncBoundary>
      </Panel>
    </div>
  );
}
