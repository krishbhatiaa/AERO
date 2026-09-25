export type DataKind = "OBSERVED" | "REANALYSIS" | "FORECAST" | "MODEL_PREDICTION" | "SYNTHETIC_DEMO";
export type Severity = "LOW" | "MODERATE" | "SEVERE";
export type Confidence = "HIGH" | "MEDIUM" | "LOW";
export type CapabilityStatus =
  | "IMPLEMENTED"
  | "PARTIALLY_IMPLEMENTED"
  | "REQUIRES_REAL_DATA"
  | "REQUIRES_GPU_TRAINING"
  | "RESEARCH_EXTENSION";

export interface Meta {
  request_id: string;
  page?: number;
  page_size?: number;
  total?: number;
}
export interface Envelope<T> {
  data: T;
  meta: Meta;
}
export interface Problem {
  type: string;
  title: string;
  status: number;
  code: string;
  detail: string;
  request_id: string;
  errors?: { loc: string[]; msg: string; type: string }[];
}

export interface Provenance {
  data_source: string;
  data_kind: DataKind;
  dataset_id: string | null;
  dataset_version: string | null;
  initialization_time: string | null;
  valid_time?: string | null;
  model_version: string | null;
  model_checkpoint: string | null;
  checkpoint_sha256: string | null;
  preprocess_config_hash: string | null;
  pipeline_config_hash: string | null;
  git_sha: string | null;
  notes: string[];
  created_at: string;
  timezone: "UTC";
}

export interface EventSummary {
  id: string;
  event_type: string;
  status: string;
  severity: Severity;
  severity_is_official: false;
  data_kind: DataKind;
  first_valid_time: string;
  last_valid_time: string;
  peak_intensity: { value: number; unit: string };
  peak_lead_hours: number;
  peak_valid_time: string;
  max_area_km2: number;
  centroid: { lat: number; lon: number };
  n_steps: number;
  probability: number;
  confidence: Confidence;
  risk_score: number;
  attributes: { tracked_by: string; detector: string; min_msl_hpa: number; max_wind_ms: number; cyclone_like_signature: boolean; note: string };
  provenance: Provenance;
  disclaimer: string;
}

export type Position = [number, number];
export type Geometry =
  | { type: "Point"; coordinates: Position }
  | { type: "LineString"; coordinates: Position[] }
  | { type: "MultiLineString"; coordinates: Position[][] }
  | { type: "Polygon"; coordinates: Position[][] }
  | { type: "MultiPolygon"; coordinates: Position[][][] };
export interface Feature<P = Record<string, unknown>> {
  type: "Feature";
  properties: P;
  geometry: Geometry;
}
export interface FeatureCollection<P = Record<string, unknown>> {
  type: "FeatureCollection";
  features: Feature<P>[];
}

export interface TrackFeatureProps {
  kind: "tracked" | "extrapolation" | "tracked_point" | "extrapolated_point" | "uncertainty_envelope" | "ensemble_members";
  label?: string;
  data_kind?: DataKind;
  lead_hours?: number;
  valid_time?: string;
  speed_kmh?: number;
  bearing_deg?: number;
  accel_kmh2?: number;
  area_km2?: number;
  max_intensity?: number;
  intensity_unit?: string;
  confidence?: number;
  filter_uncertainty_radius_km?: number;
  ensemble_radius_km_p90?: number | null;
  member_agreement?: number;
  min_msl_hpa?: number;
  max_wind_ms?: number;
}
export interface TrajectoryData extends FeatureCollection<TrackFeatureProps> {
  meta: { event_id: string; data_kind: DataKind; timezone: "UTC"; initialization_time: string };
}

export interface RegionHit {
  region_id: string;
  name: string;
  code: string;
  level: string;
  intersect_area_km2: number;
  fraction_of_region: number;
  fraction_of_polygon: number;
}
export interface RiskOut {
  category: Severity;
  score: number;
  hazard: number;
  components: Record<string, number>;
  confidence: Confidence;
  rationale: string[];
  disclaimer: string;
  config_digest: string;
  is_official_warning_category: false;
}
export interface ImpactData extends FeatureCollection<{ kind: "impact" | "risk" | "uncertainty"; area_km2: number; lead_hours: number; valid_time: string }> {
  regions: { impact: RegionHit[]; risk: RegionHit[] };
  uncertainty_radius_km: number;
  risk: RiskOut;
  meta: { lead_hours: number; data_kind: DataKind; boundary_source: string; polygon_definitions: Record<string, string> };
}

export interface UncertaintyStep {
  lead_hours: number;
  valid_time: string;
  member_agreement: number;
  n_members_detected: number;
  ensemble_radius_km_p90: number | null;
  ensemble_rms_spread_km: number | null;
  peak_tp_p10_p50_p90_mm: [number, number, number];
  control_peak_tp_mm: number;
  efi_style_max: number;
  confidence: Confidence;
}
export interface UncertaintyData {
  event_id: string;
  data_kind: DataKind;
  n_members: number;
  steps: UncertaintyStep[];
  notes: string[];
}

export interface ExplainFactor {
  name: string;
  value: number | string | null;
  unit: string;
  detail: string;
}
export interface ExplainData {
  event_id: string;
  lead_hours: number;
  valid_time: string;
  data_kind: DataKind;
  factors: ExplainFactor[];
  notes: string[];
}

export interface MetricStat {
  mean: number;
  ci_low: number;
  ci_high: number;
}
export type MetricMap = Record<string, MetricStat>;
export interface PhysicsReport {
  nonneg_violation_fraction: number;
  conservation_max_abs_mm: number;
  conservation_max_rel: number;
  wind_divergence_max_abs_s1: number | null;
  wind_divergence_mean_abs_s1: number | null;
  checks_passed: boolean;
}
export interface DownscaledSummary {
  event_id: string;
  data_kind: DataKind;
  default_method: string;
  learned_model_available: boolean;
  notice: string;
  source_resolution_km: [number, number];
  target_resolution_km: [number, number];
  methods: { method: string; metrics: MetricMap }[];
  physics_checks: Record<string, PhysicsReport>;
}

export interface FieldPayload {
  product: "forecast" | "truth" | "downscaled" | "anomaly";
  variable: string;
  method: string | null;
  units: string;
  lead_hours: number;
  valid_time: string;
  timezone: "UTC";
  bounds: [number, number, number, number];
  shape: [number, number];
  row_order: "south_to_north";
  resolution_km: { north_south: number; east_west: number };
  data_kind: DataKind;
  label: string;
  min: number;
  max: number;
  encoding: "float32-le-base64";
  values_b64: string;
}

export interface ForecastRun {
  id: string;
  source: string;
  data_kind: DataKind;
  initialization_time: string;
  timezone: "UTC";
  lead_hours: number[];
  valid_times: string[];
  n_members: number;
  variables: Record<string, string>;
  extrapolation_hours: number[];
  provenance: Provenance;
}

export interface Alert {
  id: string;
  event_id: string;
  event_type: string;
  severity: Severity;
  severity_is_official: false;
  location: { centroid: { lat: number; lon: number }; peak_lead_hours: number; regions: string[]; summary: string };
  affected_area: { km2_footprint_max: number; regions_risk_polygon: RegionHit[]; regions_impact_polygon: RegionHit[]; boundary_source: string };
  forecast_window: { start: string; end: string; timezone: "UTC" };
  probability: number;
  confidence: Confidence;
  uncertainty: { position_radius_km_p90: number; risk_polygon_buffer_km: number; uncertainty_polygon_buffer_km: number };
  risk: RiskOut;
  source: string;
  model_version: string;
  data_kind: DataKind;
  status: string;
  created_at: string;
  verification: string;
  disclaimer: string;
  provenance: Provenance;
}

export interface JobRecord {
  id: string;
  type: string;
  status: "PENDING" | "RUNNING" | "SUCCEEDED" | "FAILED";
  progress: number;
  current_step: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  steps: { name: string; at: string; fraction: number }[];
  result: Record<string, unknown> | null;
  error: string | null;
  params: Record<string, unknown>;
}

export interface ModelEntry {
  name: string;
  version: string;
  kind: string;
  architecture: string;
  status: string;
  learned: boolean;
  parameters: number;
  checkpoint: string | null;
  training_dataset: string | null;
  created_at: string;
  metrics: Record<string, number>;
}
export interface DatasetEntry {
  id: string;
  name: string;
  source: string;
  data_kind: DataKind;
  origin: string;
  created_at: string;
  variables: Record<string, string>;
  temporal_extent?: { start: string; end: string } | null;
  validation: { ok: boolean; n_findings: number };
  grid?: { dlat: number; dlon: number; nlat: number; nlon: number; resolution_km: [number, number] };
  n_members?: number;
  note?: string;
}
export interface SourceStatus {
  name: string;
  data_kind: DataKind;
  status: "AVAILABLE" | "DOWNLOADABLE" | "ACCESS_REQUIRED" | "NOT_CONFIGURED";
  message: string;
  nominal_resolution_deg: number | null;
  access: string;
  variables: string[];
}
export interface DataSourcesData {
  sources: SourceStatus[];
  target_source_resolution: { requested: string; used: string; substituted: boolean; message: string };
}

export interface DownscalingEval {
  data_kind: DataKind;
  n_frames: number;
  lead_hours: number[];
  caveat: string;
  learned_models_evaluated: string[];
  methods: { method: string; metrics: MetricMap; per_frame: Record<string, number[]> }[];
}
export interface TrackingEval {
  data_kind: DataKind;
  summary: Record<string, number | string>;
  hindcast: { horizon_steps: string[]; kalman_km: Record<string, number>; persistence_km: Record<string, number>; n_samples: Record<string, number> };
  caveat: string;
}

export interface DependencyStatus {
  status: "ok" | "down" | "not_configured";
  detail?: string;
  [k: string]: unknown;
}
export interface ReadyData {
  ready: boolean;
  dependencies: Record<string, DependencyStatus>;
}
export interface HealthData {
  status: string;
  version: string;
  uptime_s: number;
  git_sha: string | null;
  mode: { demo_mode: boolean; real_data_mode: boolean; env: string; data_kind_in_use: DataKind; auth_mode: string; note?: string };
}
export interface CapabilitiesData {
  mode: HealthData["mode"];
  capabilities: { id: string; name: string; status: CapabilityStatus; detail: string }[];
  counts: Partial<Record<CapabilityStatus, number>>;
}

export interface WsMessage {
  type: string;
  ts_utc: string;
  request_id: string;
  payload: Record<string, unknown> & { channel?: string; job_id?: string; step?: string; fraction?: number; status?: string };
}
