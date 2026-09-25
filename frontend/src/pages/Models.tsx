import { AsyncBoundary } from "@/components/AsyncBoundary";
import { Panel } from "@/components/Panel";
import { PipelineDiagram } from "@/features/PipelineDiagram";
import { useCapabilities, useModels } from "@/hooks/queries";
import { fmt } from "@/lib/utils";

export function Models(): JSX.Element {
  const models = useModels();
  const caps = useCapabilities();
  return (
    <div className="mx-auto max-w-6xl space-y-4 p-4">
      <div><h1 className="text-head-lg">Models & pipeline</h1><p className="text-body-sm text-on-surface-variant">Every advanced component has a simpler baseline that always works. A learned model is promoted only after it beats its baseline on held-out data. <b>No learned model has been trained yet</b>, so every registry entry below is a classical baseline.</p></div>
      <Panel title="Pipeline: input → risk (status of each stage)"><AsyncBoundary query={caps} label="capabilities">{(c) => <PipelineDiagram caps={c} />}</AsyncBoundary></Panel>
      <Panel title="Model registry">
        <AsyncBoundary query={models} label="model registry" isEmpty={(d) => d.length === 0}>
          {(rows) => (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-left text-body-sm">
                <caption className="sr-only">Registered models and baselines</caption>
                <thead><tr className="text-label-header uppercase text-on-surface-variant">{["Name", "Kind", "Architecture", "Version", "Status", "Learned", "Params", "Checkpoint", "Key metrics (synthetic frames)"].map((h) => <th key={h} scope="col" className="border-b border-outline-variant px-2 py-1.5">{h}</th>)}</tr></thead>
                <tbody>
                  {rows.map((m) => (
                    <tr key={m.name} className="odd:bg-surface-container-low align-top">
                      <th scope="row" className="px-2 py-1.5 text-left font-mono text-label-num-md font-semibold">{m.name}</th>
                      <td className="px-2 py-1.5">{m.kind.replace("_", " ")}</td><td className="px-2 py-1.5 text-on-surface-variant">{m.architecture}</td>
                      <td className="px-2 py-1.5 font-mono">{m.version}</td><td className="px-2 py-1.5 font-mono text-label-num-md">{m.status}</td>
                      <td className="px-2 py-1.5">{m.learned ? "yes" : "no"}</td><td className="px-2 py-1.5 font-mono">{m.parameters}</td><td className="px-2 py-1.5 font-mono">{m.checkpoint ?? "none"}</td>
                      <td className="px-2 py-1.5 font-mono text-label-num-md">{Object.entries(m.metrics).slice(0, 3).map(([k, v]) => `${k}=${fmt(v, 2)}`).join(" · ") || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </AsyncBoundary>
      </Panel>
    </div>
  );
}
