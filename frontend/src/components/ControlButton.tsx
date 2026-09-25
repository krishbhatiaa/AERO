import * as Tooltip from "@radix-ui/react-tooltip";
import { Loader2 } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

interface Props {
  label: string;
  onClick?: () => void;
  icon?: LucideIcon;
  active?: boolean;
  toggle?: boolean;
  loading?: boolean;
  disabled?: boolean;
  disabledReason?: string;
  tooltip?: string;
  variant?: "solid" | "ghost" | "tonal";
  children?: ReactNode;
  className?: string;
  size?: "sm" | "md";
}

/** Accessible button with hover, active (aria-pressed for toggles), focus-visible, loading and disabled states plus tooltip. */
export function ControlButton({ label, onClick, icon: Icon, active, toggle, loading, disabled, disabledReason, tooltip, variant = "tonal", children, className, size = "md" }: Props): JSX.Element {
  const isDisabled = !!disabled || !!loading;
  const btn = (
    <button
      type="button"
      onClick={onClick}
      disabled={isDisabled}
      aria-label={label}
      aria-pressed={toggle ? !!active : undefined}
      aria-busy={loading || undefined}
      aria-disabled={isDisabled || undefined}
      className={cn(
        "inline-flex items-center justify-center gap-1.5 rounded border font-mono font-semibold uppercase tracking-wide transition-colors duration-150",
        size === "sm" ? "h-6 px-2 text-label-num-sm" : "h-7 px-2.5 text-label-num-md",
        variant === "solid" && "border-transparent bg-primary text-on-primary hover:bg-primary-container",
        variant === "tonal" && "border-outline-variant bg-surface-container-lowest text-on-surface hover:bg-surface-container",
        variant === "ghost" && "border-transparent bg-transparent text-on-surface-variant hover:bg-surface-container hover:text-on-surface",
        active && "border-primary bg-primary text-on-primary hover:bg-primary-container",
        isDisabled && "cursor-not-allowed opacity-50",
        className,
      )}
    >
      {loading ? <Loader2 aria-hidden className="h-3.5 w-3.5 animate-spin" /> : Icon ? <Icon aria-hidden className="h-3.5 w-3.5" /> : null}
      {children ?? null}
    </button>
  );
  const tip = disabled && disabledReason ? disabledReason : tooltip;
  if (!tip) return btn;
  return (
    <Tooltip.Root delayDuration={250}>
      <Tooltip.Trigger asChild>{isDisabled ? <span tabIndex={0} className="inline-flex">{btn}</span> : btn}</Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content sideOffset={6} className="z-[100] max-w-[240px] rounded bg-inverse-surface px-2 py-1 text-body-xs text-inverse-on-surface shadow-lg">
          {tip}
          <Tooltip.Arrow className="fill-inverse-surface" />
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}
