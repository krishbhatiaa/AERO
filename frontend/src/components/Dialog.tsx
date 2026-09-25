import * as RD from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { ReactNode } from "react";

/** Accessible modal (focus trap, Escape to close, labelled title/description) built on Radix. */
export function Dialog({ open, onOpenChange, title, description, children }: { open: boolean; onOpenChange: (o: boolean) => void; title: string; description: string; children: ReactNode }): JSX.Element {
  return (
    <RD.Root open={open} onOpenChange={onOpenChange}>
      <RD.Portal>
        <RD.Overlay className="fixed inset-0 z-[90] bg-black/50" />
        <RD.Content className="fixed left-1/2 top-1/2 z-[91] max-h-[86vh] w-[min(720px,94vw)] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-lg border border-outline-variant bg-surface-container-lowest p-5 text-on-surface shadow-2xl">
          <div className="mb-3 flex items-start justify-between gap-4">
            <div>
              <RD.Title className="text-head-lg">{title}</RD.Title>
              <RD.Description className="mt-1 text-body-sm text-on-surface-variant">{description}</RD.Description>
            </div>
            <RD.Close aria-label="Close dialog" className="rounded p-1 text-on-surface-variant hover:bg-surface-container"><X aria-hidden className="h-4 w-4" /></RD.Close>
          </div>
          {children}
        </RD.Content>
      </RD.Portal>
    </RD.Root>
  );
}
