import {
  Camera,
  Crosshair,
  Globe,
  Maximize,
  MapPin,
  Monitor,
  Navigation,
  RotateCcw,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { useState } from "react";

import { ControlButton } from "@/components/ControlButton";

interface MapControlsProps {
  onZoomIn: () => void;
  onZoomOut: () => void;
  onReset: () => void;
  onRecenter?: () => void;
  onFullscreen?: () => void;
  onScreenshot?: () => void;
  onRegionZoom?: (region: "india" | "bengal" | "global") => void;
  recenterDisabled?: boolean;
  recenterDisabledReason?: string;
}

const REGIONS = [
  { id: "india" as const, label: "India", icon: MapPin, bounds: [68, 6, 98, 37] as [number, number, number, number] },
  { id: "bengal" as const, label: "Bay of Bengal", icon: Navigation, bounds: [80, 5, 95, 22] as [number, number, number, number] },
  { id: "global" as const, label: "Global", icon: Globe, bounds: [-180, -60, 180, 75] as [number, number, number, number] },
] as const;

export function MapControls({
  onZoomIn,
  onZoomOut,
  onReset,
  onRecenter,
  onFullscreen,
  onScreenshot,
  onRegionZoom,
  recenterDisabled = false,
  recenterDisabledReason,
}: MapControlsProps): JSX.Element {
  const [showRegions, setShowRegions] = useState(false);
  const [showKeyboardHelp, setShowKeyboardHelp] = useState(false);

  return (
    <div className="absolute right-2 top-2 z-10 flex flex-col gap-1">
      <div className="flex flex-col gap-1 rounded border border-outline-variant/60 bg-surface-container-lowest/95 p-1 shadow">
        <ControlButton label="Zoom in" icon={ZoomIn} variant="ghost" size="sm" tooltip="Zoom in (+)" onClick={onZoomIn} />
        <ControlButton label="Zoom out" icon={ZoomOut} variant="ghost" size="sm" tooltip="Zoom out (-)" onClick={onZoomOut} />
        <ControlButton label="Reset view" icon={Maximize} variant="ghost" size="sm" tooltip="Reset view (0)" onClick={onReset} />
        <ControlButton
          label="Recenter on event"
          icon={Crosshair}
          variant="ghost"
          size="sm"
          tooltip="Recenter on the event at this lead time"
          disabled={recenterDisabled}
          disabledReason={recenterDisabledReason}
          onClick={onRecenter}
        />
      </div>

      <div className="relative">
        <ControlButton
          label="Zoom to region"
          icon={MapPin}
          variant="ghost"
          size="sm"
          tooltip="Zoom to predefined region"
          onClick={() => setShowRegions(!showRegions)}
        />
        {showRegions && (
          <div className="absolute right-0 top-full mt-1 flex flex-col gap-1 rounded border border-outline-variant/60 bg-surface-container-lowest/95 p-1 shadow">
            {REGIONS.map((r) => (
              <ControlButton
                key={r.id}
                label={r.label}
                icon={r.icon}
                variant="ghost"
                size="sm"
                tooltip={`Zoom to ${r.label}`}
                onClick={() => {
                  onRegionZoom?.(r.id);
                  setShowRegions(false);
                }}
              />
            ))}
          </div>
        )}
      </div>

      <ControlButton
        label="Toggle fullscreen"
        icon={Monitor}
        variant="ghost"
        size="sm"
        tooltip="Toggle fullscreen (F)"
        onClick={onFullscreen}
      />

      <ControlButton
        label="Export screenshot"
        icon={Camera}
        variant="ghost"
        size="sm"
        tooltip="Export map as PNG"
        onClick={onScreenshot}
      />

      <ControlButton
        label="Keyboard shortcuts"
        icon={RotateCcw}
        variant="ghost"
        size="sm"
        tooltip="Show keyboard shortcuts"
        onClick={() => setShowKeyboardHelp(!showKeyboardHelp)}
      />

      {showKeyboardHelp && (
        <div className="absolute right-0 top-full mt-1 w-56 rounded border border-outline-variant/60 bg-surface-container-lowest/95 p-2 shadow">
          <div className="mb-1 text-label-header uppercase text-on-surface-variant">Keyboard Shortcuts</div>
          <dl className="space-y-0.5 text-label-num-sm">
            <div className="flex justify-between"><dt className="text-on-surface-variant">Pan</dt><dd>Arrow keys</dd></div>
            <div className="flex justify-between"><dt className="text-on-surface-variant">Zoom in</dt><dd>+ / =</dd></div>
            <div className="flex justify-between"><dt className="text-on-surface-variant">Zoom out</dt><dd>-</dd></div>
            <div className="flex justify-between"><dt className="text-on-surface-variant">Reset</dt><dd>0</dd></div>
            <div className="flex justify-between"><dt className="text-on-surface-variant">Fullscreen</dt><dd>F</dd></div>
            <div className="flex justify-between"><dt className="text-on-surface-variant">Screenshot</dt><dd>S</dd></div>
          </dl>
        </div>
      )}
    </div>
  );
}
