import { PRECIP_STOPS } from "@/lib/colors";
import type { DecodedField } from "@/lib/field";
import { fitView } from "@/lib/geo";
import { useSize } from "@/hooks/useSize";
import type { FeatureCollection, ImpactData, TrajectoryData } from "@/types/api";
import { useUi } from "@/stores/ui";

import { LandLayer, MapOverlay, WorldLandLayer } from "./MapOverlay";
import { RasterCanvas } from "./RasterCanvas";

interface Props {
  bounds: [number, number, number, number];
  lead: number;
  field?: DecodedField;
  trajectory?: TrajectoryData;
  impact?: ImpactData;
  countries?: FeatureCollection;
  states?: FeatureCollection<{ name: string }>;
  ariaLabel: string;
  className?: string;
}

/** Non-interactive map used on detail pages (event trajectory, 12 km vs 5 km panels). */
export function StaticMap({ bounds, lead, field, trajectory, impact, countries, states, ariaLabel, className }: Props): JSX.Element {
  const [ref, size] = useSize<HTMLDivElement>();
  const layers = useUi((s) => s.layers);
  const view = fitView(bounds, size, 0.98);
  return (
    <div ref={ref} role="img" aria-label={ariaLabel} className={`relative overflow-hidden rounded border border-outline-variant/60 bg-[rgb(var(--map-sea))] ${className ?? "h-64"}`}>
      <WorldLandLayer view={view} size={size} />
      {layers.boundaries && <LandLayer view={view} size={size} countries={countries} />}
      <RasterCanvas field={field} stops={PRECIP_STOPS} view={view} size={size} />
      <MapOverlay view={view} size={size} layers={{ ...layers, wind: false, graticule: false }} lead={lead} countries={countries} states={states} trajectory={trajectory} impact={impact} measure={[]} probe={null} />
    </div>
  );
}
