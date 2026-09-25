import { keepPreviousData, useMutation, useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";

import { apiGet, apiPost, ApiClientError } from "@/lib/api";
import { decodeField, type DecodedField } from "@/lib/field";
import type {
  Alert, CapabilitiesData, DatasetEntry, DataSourcesData, DownscaledSummary, DownscalingEval, EventSummary, ExplainData, FieldPayload,
  ForecastRun, HealthData, ImpactData, JobRecord, ModelEntry, ReadyData, TrackingEval, TrajectoryData, UncertaintyData,
} from "@/types/api";

/** 4xx and offline errors are not retried; transient failures get one retry. */
export function retryPolicy(count: number, err: Error): boolean {
  if (err instanceof ApiClientError && (err.offline || (err.status >= 400 && err.status < 500))) return false;
  return count < 1;
}

const get = <T,>(path: string, params?: Record<string, string | number | undefined>) => async (): Promise<T> => (await apiGet<T>(path, params)).data;
const list = <T,>(path: string) => async (): Promise<T[]> => (await apiGet<T[]>(path, { page_size: 200 })).data;

export const useHealth = (): UseQueryResult<HealthData> => useQuery({ queryKey: ["health"], queryFn: get<HealthData>("/health"), refetchInterval: 15_000 });
export const useReady = (): UseQueryResult<ReadyData> =>
  useQuery({
    queryKey: ["ready"],
    queryFn: get<ReadyData>("/ready"),
    refetchInterval: 15_000,
  });
export const useCapabilities = (): UseQueryResult<CapabilitiesData> => useQuery({ queryKey: ["capabilities"], queryFn: get<CapabilitiesData>("/capabilities"), staleTime: 300_000 });
export const useForecast = (): UseQueryResult<ForecastRun | undefined> =>
  useQuery({ queryKey: ["forecasts"], queryFn: async () => (await list<ForecastRun>("/forecasts")())[0] });

export interface EventFilters {
  severity?: string;
  event_type?: string;
  sort?: string;
}
export const useEvents = (f: EventFilters = {}): UseQueryResult<EventSummary[]> =>
  useQuery({ queryKey: ["events", f], queryFn: async () => (await apiGet<EventSummary[]>("/events", { page_size: 200, ...f })).data, placeholderData: keepPreviousData });
export const useEvent = (id: string | null): UseQueryResult<EventSummary> => useQuery({ queryKey: ["event", id], queryFn: get<EventSummary>(`/events/${id}`), enabled: !!id });
export const useTrajectory = (id: string | null): UseQueryResult<TrajectoryData> => useQuery({ queryKey: ["trajectory", id], queryFn: get<TrajectoryData>(`/events/${id}/trajectory`), enabled: !!id });
export const useImpact = (id: string | null, lead: number | undefined): UseQueryResult<ImpactData> =>
  useQuery({ queryKey: ["impact", id, lead], queryFn: get<ImpactData>(`/events/${id}/impact`, { lead_hours: lead }), enabled: !!id && lead !== undefined, retry: retryPolicy, placeholderData: keepPreviousData });
export const useUncertainty = (id: string | null): UseQueryResult<UncertaintyData> => useQuery({ queryKey: ["uncertainty", id], queryFn: get<UncertaintyData>(`/events/${id}/uncertainty`), enabled: !!id });
export const useExplain = (id: string | null, lead: number | undefined): UseQueryResult<ExplainData> =>
  useQuery({ queryKey: ["explain", id, lead], queryFn: get<ExplainData>(`/events/${id}/explain`, { lead_hours: lead }), enabled: !!id && lead !== undefined, retry: retryPolicy, placeholderData: keepPreviousData });
export const useDownscaled = (id: string | null): UseQueryResult<DownscaledSummary> => useQuery({ queryKey: ["downscaled", id], queryFn: get<DownscaledSummary>(`/events/${id}/downscaled`), enabled: !!id });

export interface FieldParams {
  product: FieldPayload["product"];
  variable: string;
  lead: number | undefined;
  method?: string;
  enabled?: boolean;
}
export function useField(p: FieldParams): UseQueryResult<DecodedField> {
  return useQuery({
    queryKey: ["field", p.product, p.variable, p.lead, p.method ?? null],
    queryFn: async () => decodeField((await apiGet<FieldPayload>("/fields", { product: p.product, variable: p.variable, lead_hours: p.lead, method: p.method })).data),
    enabled: (p.enabled ?? true) && p.lead !== undefined,
    staleTime: 600_000,
    placeholderData: keepPreviousData,
    retry: retryPolicy,
  });
}

export const useAlerts = (): UseQueryResult<Alert[]> => useQuery({ queryKey: ["alerts"], queryFn: list<Alert>("/alerts") });
export const useModels = (): UseQueryResult<ModelEntry[]> => useQuery({ queryKey: ["models"], queryFn: list<ModelEntry>("/models") });
export const useDatasets = (): UseQueryResult<DatasetEntry[]> => useQuery({ queryKey: ["datasets"], queryFn: list<DatasetEntry>("/datasets") });
export const useDataSources = (): UseQueryResult<DataSourcesData> => useQuery({ queryKey: ["data-sources"], queryFn: get<DataSourcesData>("/data-sources") });
export const useDownscalingEval = (): UseQueryResult<DownscalingEval> => useQuery({ queryKey: ["eval-downscaling"], queryFn: get<DownscalingEval>("/evaluation/downscaling") });
export const useTrackingEval = (): UseQueryResult<TrackingEval> => useQuery({ queryKey: ["eval-tracking"], queryFn: get<TrackingEval>("/evaluation/tracking") });
export const useJobs = (): UseQueryResult<JobRecord[]> => useQuery({ queryKey: ["jobs"], queryFn: list<JobRecord>("/jobs"), refetchInterval: 4_000 });

export function useRunPipeline() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (v: { scenario_seed: number; n_members: number }) => (await apiPost<JobRecord>("/predictions", v)).data,
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["jobs"] }),
  });
}
