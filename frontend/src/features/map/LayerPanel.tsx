import { Hand, LocateFixed, Ruler } from "lucide-react";

import { ControlButton } from "@/components/ControlButton";
import { cn } from "@/lib/utils";
import { useUi, type Basemap, type Layers, type SingleSource, type Tool } from "@/stores/ui";

const BASEMAPS: { id: Basemap; label: string; icon: string; desc: string }[] = [
  { id: "standard", label: "Standard", icon: "🗺️", desc: "Vector map" },
  { id: "satellite", label: "Satellite", icon: "🛰️", desc: "Earth orbital" },
  { id: "terrain", label: "Terrain", icon: "🏔️", desc: "Topographic" },
  { id: "dark", label: "Dark Radar", icon: "🌙", desc: "Night ops" },
  { id: "nautical", label: "Nautical", icon: "⚓", desc: "Marine sea" },
];

const LAYERS: { key: keyof Layers; label: string; hint: string }[] = [
  { key: "precip", label: "Precipitation raster", hint: "6-hourly accumulation (mm)" },
  { key: "anomaly", label: "Anomaly score (P95+)", hint: "coarse control forecast vs climatology" },
  { key: "impact", label: "Impact / risk / uncertainty", hint: "polygons at the current lead time" },
  { key: "track", label: "Centroid & trajectory", hint: "Kalman-filtered track + extrapolation" },
  { key: "envelope", label: "Uncertainty envelope", hint: "ensemble p90 radius, then filter 95 % radius" },
  { key: "members", label: "Ensemble member tracks", hint: "10 synthetic perturbed members" },
  { key: "wind", label: "10 m wind vectors", hint: "coarse forecast, ≥ 8 m/s" },
  { key: "boundaries", label: "Boundaries (Natural Earth)", hint: "not official boundaries" },
  { key: "graticule", label: "Graticule", hint: "" },
];

const TOOLS: { tool: Tool; label: string; icon: typeof Hand; tip: string }[] = [
  { tool: "pan", label: "Pan", icon: Hand, tip: "Drag to pan, wheel to zoom" },
  { tool: "probe", label: "Probe", icon: LocateFixed, tip: "Click to read field values at a point" },
  { tool: "measure", label: "Measure", icon: Ruler, tip: "Click two points for great-circle distance" },
];

export function LayerPanel(): JSX.Element {
  const { layers, toggleLayer, tool, setTool, compare, setCompare, single, setSingle, basemap, setBasemap } = useUi();
  const active = Object.values(layers).filter(Boolean).length;
  return (
    <div className="flex h-full flex-col bg-surface-container-lowest">
      {/* Basemap Switcher */}
      <div className="border-b border-outline-variant/30 bg-surface-container-low/40 p-2.5">
        <div className="mb-2 flex items-center justify-between text-label-header uppercase text-on-surface-variant">
          <span className="font-bold tracking-wider">Map Style</span>
          <span className="font-mono text-primary text-[10px] uppercase font-bold">{basemap}</span>
        </div>
        <div className="grid grid-cols-5 gap-1" role="radiogroup" aria-label="Map style">
          {BASEMAPS.map((b) => (
            <button
              key={b.id}
              type="button"
              role="radio"
              aria-checked={basemap === b.id}
              onClick={() => setBasemap(b.id)}
              title={`${b.label}: ${b.desc}`}
              className={cn(
                "flex flex-col items-center justify-center p-1.5 rounded-lg border text-center transition-all",
                basemap === b.id
                  ? "border-primary bg-primary/10 text-primary font-bold shadow-xs scale-102"
                  : "border-outline-variant/40 bg-surface-container-lowest hover:bg-surface-container text-on-surface-variant hover:text-on-surface"
              )}
            >
              <span className="text-sm leading-none mb-1">{b.icon}</span>
              <span className="text-[9px] font-medium leading-tight truncate w-full">{b.label}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="border-b border-outline-variant/30 bg-surface-container-low p-2">
        <div className="mb-1 text-label-header uppercase text-on-surface-variant">Tool dock</div>
        <div className="flex flex-wrap gap-1" role="group" aria-label="Map tools">
          {TOOLS.map((t) => <ControlButton key={t.tool} label={t.label} icon={t.icon} toggle active={tool === t.tool} tooltip={t.tip} onClick={() => setTool(t.tool)}>{t.label}</ControlButton>)}
        </div>
      </div>
      <div className="border-b border-outline-variant/30 p-2">
        <div className="mb-1 text-label-header uppercase text-on-surface-variant">Comparison</div>
        <div className="flex rounded bg-surface-container-low p-0.5" role="group" aria-label="Comparison mode">
          {(["split", "single"] as const).map((m) => (
            <button key={m} type="button" aria-pressed={compare === m} onClick={() => setCompare(m)} className={cn("flex-1 rounded px-2 py-1 font-mono text-label-num-sm font-semibold", compare === m ? "bg-primary text-on-primary" : "text-on-surface-variant hover:text-on-surface")}>{m === "split" ? "SPLIT WIPE" : "SINGLE"}</button>
          ))}
        </div>
        {compare === "single" && (
          <div className="mt-1.5">
            <label className="text-body-xs text-on-surface-variant" htmlFor="single-source">Raster source</label>
            <select id="single-source" value={single} onChange={(e) => setSingle(e.target.value as SingleSource)} className="mt-0.5 w-full rounded border border-outline-variant bg-surface-container-lowest px-1 py-1 font-mono text-label-num-md">
              <option value="coarse">Coarse forecast (~11 km)</option>
              <option value="fine">Baseline interpolation (~5.5 km)</option>
              <option value="truth">Synthetic fine truth (~5.5 km)</option>
            </select>
          </div>
        )}
      </div>
      <div className="flex items-center justify-between bg-surface-container-high/30 p-2"><span className="text-label-header uppercase">Active layers</span><span className="font-mono text-label-num-sm font-medium text-primary">{active} / {LAYERS.length}</span></div>
      <fieldset className="min-h-0 flex-1 space-y-0.5 overflow-y-auto p-2">
        <legend className="sr-only">Map layers</legend>
        {LAYERS.map((l) => {
          const key = l.key;
          const checked = layers[key];
          return (
            <label key={l.key} className={cn("flex cursor-pointer items-start gap-2 rounded p-1 hover:bg-surface-container", checked ? "bg-surface-container-low" : "")}>
              <input type="checkbox" checked={checked} onChange={() => toggleLayer(key)} className="mt-0.5 h-3.5 w-3.5 accent-[rgb(var(--c-primary))]" />
              <span><span className={cn("block text-body-xs font-medium", !checked && "text-on-surface-variant")}>{l.label}</span>{l.hint && <span className="block text-[10px] text-on-surface-variant">{l.hint}</span>}</span>
            </label>
          );
        })}
      </fieldset>
    </div>
  );
}
