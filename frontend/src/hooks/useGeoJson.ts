import { useQuery } from "@tanstack/react-query";

import type { FeatureCollection } from "@/types/api";

/** Static boundary files served from /data (Natural Earth, public domain; NOT official boundaries). */
export function useGeoJson<P = Record<string, unknown>>(name: string) {
  return useQuery({
    queryKey: ["geojson", name],
    queryFn: async (): Promise<FeatureCollection<P>> => {
      const res = await fetch(`/data/${name}`);
      if (!res.ok) throw new Error(`boundary file ${name} unavailable`);
      return (await res.json()) as FeatureCollection<P>;
    },
    staleTime: Infinity,
    retry: 1,
  });
}
