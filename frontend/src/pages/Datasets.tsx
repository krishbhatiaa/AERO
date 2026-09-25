import { AsyncBoundary } from "@/components/AsyncBoundary";
import { DataKindBadge } from "@/components/DataKindBadge";
import { Panel } from "@/components/Panel";
import { TimeStamp } from "@/components/TimeStamp";
import { useDatasets, useDataSources } from "@/hooks/queries";
import { cn } from "@/lib/utils";
import type { SourceStatus } from "@/types/api";

const STATUS_CLS: Record<SourceStatus["status"], string> = {
  AVAILABLE: "border-primary/60 text-primary", DOWNLOADABLE: "border-secondary/60 text-secondary",
  ACCESS_REQUIRED: "border-tertiary/70 text-tertiary", NOT_CONFIGURED: "border-outline text-on-surface-variant",
};

export function Datasets(): JSX.Element {
  const sources = useDataSources();
  const datasets = useDatasets();
  return (
    <div className="mx-auto max-w-6xl space-y-4 p-4">
      <div><h1 className="text-head-lg">Datasets & data sources</h1><p className="text-body-sm text-on-surface-variant">Restricted sources are never scraped or bypassed. If a source is unavailable the system says so and names the dataset it uses instead; it never relabels one dataset as another.</p></div>
      <AsyncBoundary query={sources} label="data sources">
        {(s) => (
          <>
            <div role="status" className="rounded border border-outline-variant bg-surface-container-low p-3 text-body-md"><b>Target source resolution: </b>{s.target_source_resolution.message}</div>
            <ul className="grid gap-2 md:grid-cols-2 lg:grid-cols-3">
              {s.sources.map((x) => (
                <li key={x.name} className="flex flex-col gap-1.5 rounded border border-outline-variant/60 bg-surface-container-lowest p-3">
                  <div className="flex items-center justify-between"><span className="font-semibold">{x.name}</span><DataKindBadge kind={x.data_kind} compact /></div>
                  <span className={cn("w-fit rounded border px-1.5 py-[1px] font-mono text-label-num-sm font-bold", STATUS_CLS[x.status])}>{x.status.replace("_", " ")}</span>
                  <p className="text-body-xs text-on-surface-variant">{x.message}</p>
                  {x.nominal_resolution_deg !== null && <p className="font-mono text-label-num-sm text-on-surface-variant">nominal ≈ {x.nominal_resolution_deg}° grid</p>}
                  <p className="text-body-xs">{x.access}</p>
                </li>
              ))}
            </ul>
          </>
        )}
      </AsyncBoundary>
      <Panel title="Catalogued datasets">
        <AsyncBoundary query={datasets} label="datasets" isEmpty={(d) => d.length === 0}>
          {(rows) => (
            <div className="overflow-x-auto"><table className="w-full border-collapse text-left text-body-sm">
              <caption className="sr-only">Datasets known to the platform</caption>
              <thead><tr className="text-label-header uppercase text-on-surface-variant">{["Dataset", "Source", "Kind", "Variables", "Grid", "Temporal extent (UTC)", "Validation"].map((h) => <th key={h} scope="col" className="border-b border-outline-variant px-2 py-1.5">{h}</th>)}</tr></thead>
              <tbody>{rows.map((d) => (
                <tr key={d.id} className="odd:bg-surface-container-low align-top">
                  <th scope="row" className="px-2 py-1.5 text-left"><div className="font-semibold">{d.name}</div><div className="font-mono text-label-num-sm text-on-surface-variant">{d.id}</div></th>
                  <td className="px-2 py-1.5">{d.source}</td><td className="px-2 py-1.5"><DataKindBadge kind={d.data_kind} compact /></td>
                  <td className="px-2 py-1.5 font-mono text-label-num-md">{Object.entries(d.variables).map(([k, u]) => `${k} [${u}]`).join(", ")}</td>
                  <td className="px-2 py-1.5 font-mono text-label-num-md">{d.grid ? `${d.grid.nlat}×${d.grid.nlon} · ${d.grid.resolution_km[0].toFixed(1)} km` : "—"}</td>
                  <td className="px-2 py-1.5">{d.temporal_extent ? <><TimeStamp iso={d.temporal_extent.start} compact /> → <TimeStamp iso={d.temporal_extent.end} compact /></> : "—"}</td>
                  <td className="px-2 py-1.5 font-mono text-label-num-md">{d.validation.ok ? "OK" : "FAILED"} · {d.validation.n_findings} finding(s)</td>
                </tr>))}</tbody>
            </table></div>
          )}
        </AsyncBoundary>
      </Panel>
    </div>
  );
}
