import { Table2 } from "lucide-react";
import { useId, useState, type ReactNode } from "react";

import { cn } from "@/lib/utils";

interface Props {
  title: string;
  description: string;
  chart: ReactNode;
  table: { headers: string[]; rows: (string | number)[][] };
  className?: string;
}

/** Figure with a caption and a "view as table" switch, so every chart has a screen-reader friendly equivalent. */
export function ChartFrame({ title, description, chart, table, className }: Props): JSX.Element {
  const [asTable, setAsTable] = useState(false);
  const id = useId();
  return (
    <figure className={cn("rounded border border-outline-variant/60 bg-surface-container-lowest p-3", className)} aria-labelledby={id}>
      <figcaption className="mb-2 flex items-start justify-between gap-2">
        <div>
          <div id={id} className="text-label-header uppercase text-on-surface">{title}</div>
          <div className="text-body-xs text-on-surface-variant">{description}</div>
        </div>
        <button type="button" aria-pressed={asTable} onClick={() => setAsTable((v) => !v)} className="inline-flex shrink-0 items-center gap-1 rounded border border-outline-variant px-1.5 py-0.5 text-label-num-sm font-semibold uppercase hover:bg-surface-container">
          <Table2 aria-hidden className="h-3 w-3" />
          {asTable ? "Chart" : "Table"}
        </button>
      </figcaption>
      {asTable ? (
        <div className="max-h-48 overflow-auto">
          <table className="w-full border-collapse text-left font-mono text-label-num-md">
            <thead><tr>{table.headers.map((h) => <th key={h} scope="col" className="border-b border-outline-variant px-2 py-1 font-semibold">{h}</th>)}</tr></thead>
            <tbody>{table.rows.map((r, i) => <tr key={i} className="odd:bg-surface-container-low">{r.map((c, j) => <td key={j} className="px-2 py-0.5">{c}</td>)}</tr>)}</tbody>
          </table>
        </div>
      ) : (
        chart
      )}
    </figure>
  );
}
