import { useRef, useState, type ReactNode } from "react";

interface Props<T> {
  items: T[];
  rowHeight: number;
  height: number;
  overscan?: number;
  label: string;
  renderRow: (item: T, index: number) => ReactNode;
}

/** Windowed list: only visible rows (plus overscan) are in the DOM, so long lists stay cheap. */
export function VirtualList<T>({ items, rowHeight, height, overscan = 4, label, renderRow }: Props<T>): JSX.Element {
  const ref = useRef<HTMLDivElement>(null);
  const [top, setTop] = useState(0);
  const start = Math.max(0, Math.floor(top / rowHeight) - overscan);
  const end = Math.min(items.length, Math.ceil((top + height) / rowHeight) + overscan);
  return (
    <div ref={ref} role="list" aria-label={label} tabIndex={0} onScroll={(e) => setTop(e.currentTarget.scrollTop)} style={{ height, overflowY: "auto", position: "relative" }}>
      <div style={{ height: items.length * rowHeight, position: "relative" }}>
        {items.slice(start, end).map((item, i) => (
          <div key={start + i} role="listitem" style={{ position: "absolute", top: (start + i) * rowHeight, height: rowHeight, left: 0, right: 0 }}>
            {renderRow(item, start + i)}
          </div>
        ))}
      </div>
    </div>
  );
}
