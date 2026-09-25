import type { LucideIcon } from "lucide-react";
import { useId, type ReactNode } from "react";

import { cn } from "@/lib/utils";

interface Props {
  title: string;
  icon?: LucideIcon;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}

/** Titled region (landmark for screen readers) in the workstation style: thin border, dense, uppercase header label. */
export function Panel({ title, icon: Icon, right, children, className, bodyClassName }: Props): JSX.Element {
  const id = useId();
  return (
    <section aria-labelledby={id} className={cn("flex flex-col rounded border border-outline-variant/60 bg-surface-container-lowest shadow-sm", className)}>
      <header className="flex items-center justify-between gap-2 rounded-t border-b border-outline-variant/40 bg-surface-container-low px-3 py-1.5">
        <h2 id={id} className="flex items-center gap-1.5 text-label-header uppercase text-on-surface">
          {Icon && <Icon aria-hidden className="h-3.5 w-3.5 text-primary" />}
          {title}
        </h2>
        {right}
      </header>
      <div className={cn("p-3", bodyClassName)}>{children}</div>
    </section>
  );
}

export function KV({ k, v, mono = true, strong = false }: { k: string; v: ReactNode; mono?: boolean; strong?: boolean }): JSX.Element {
  return (
    <div className="flex items-baseline justify-between gap-3 py-[2px]">
      <dt className="text-body-xs text-on-surface-variant">{k}</dt>
      <dd className={cn("text-right text-body-sm", mono && "font-mono text-label-num-md", strong && "font-semibold")}>{v}</dd>
    </div>
  );
}
