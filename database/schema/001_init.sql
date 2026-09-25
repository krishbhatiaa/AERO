-- Extreme Weather Intelligence: PostgreSQL 16 + PostGIS 3 schema (SRID 4326).
-- Large multidimensional arrays are NEVER stored here: they live in object storage (Zarr/NetCDF/GRIB2);
-- this database holds metadata, geometries, alerts, registry and audit records.
-- Apply with:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f database/schema/001_init.sql
BEGIN;

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TYPE data_kind        AS ENUM ('OBSERVED', 'REANALYSIS', 'FORECAST', 'MODEL_PREDICTION', 'SYNTHETIC_DEMO');
CREATE TYPE event_type       AS ENUM ('EXTREME_RAINFALL', 'CYCLONE', 'HEATWAVE', 'COLD_WAVE', 'HIGH_WIND', 'OTHER');
CREATE TYPE severity         AS ENUM ('LOW', 'MODERATE', 'SEVERE');            -- analytical categories, NOT official warnings
CREATE TYPE confidence_class AS ENUM ('HIGH', 'MEDIUM', 'LOW');
CREATE TYPE job_status       AS ENUM ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'PARTIAL', 'CANCELLED');
CREATE TYPE finding_severity AS ENUM ('INFO', 'WARN', 'ERROR');
CREATE TYPE access_status    AS ENUM ('AVAILABLE', 'DOWNLOADABLE', 'ACCESS_REQUIRED', 'NOT_CONFIGURED');
CREATE TYPE track_source     AS ENUM ('BASELINE_KALMAN', 'GNN', 'ENSEMBLE_MEMBER', 'EXTRAPOLATION');
CREATE TYPE geometry_kind    AS ENUM ('IMPACT', 'RISK', 'UNCERTAINTY');
CREATE TYPE region_level     AS ENUM ('COUNTRY', 'STATE', 'DISTRICT', 'CITY');
CREATE TYPE user_role        AS ENUM ('viewer', 'analyst', 'admin');

CREATE TABLE data_sources (
    id                     serial PRIMARY KEY,
    name                   text UNIQUE NOT NULL,
    data_kind              data_kind NOT NULL,
    access_status          access_status NOT NULL,
    nominal_resolution_deg real,
    description            text,
    updated_at             timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE weather_variables (
    name            text PRIMARY KEY,
    long_name       text NOT NULL,
    canonical_units text NOT NULL,
    valid_min       double precision,
    valid_max       double precision
);

CREATE TABLE datasets (
    id                text PRIMARY KEY,
    source_id         integer REFERENCES data_sources (id),
    name              text NOT NULL,
    data_kind         data_kind NOT NULL,
    storage_key       text,
    checksum_sha256   char(64),
    grid              jsonb,
    dimensions        jsonb,
    geographic_extent geometry(Polygon, 4326),
    temporal_start    timestamptz,
    temporal_end      timestamptz,
    metadata          jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at        timestamptz NOT NULL DEFAULT now(),
    CHECK (temporal_end IS NULL OR temporal_start IS NULL OR temporal_end >= temporal_start)
);

CREATE TABLE dataset_variables (
    dataset_id   text REFERENCES datasets (id) ON DELETE CASCADE,
    variable     text REFERENCES weather_variables (name),
    source_units text,
    PRIMARY KEY (dataset_id, variable)
);

CREATE TABLE data_ingestion_jobs (
    id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id              integer REFERENCES data_sources (id),
    dataset_id             text REFERENCES datasets (id),
    status                 job_status NOT NULL DEFAULT 'PENDING',
    files                  jsonb NOT NULL DEFAULT '[]'::jsonb,       -- [{name,size,sha256}]
    checksum_sha256        char(64),
    preprocess_config_hash text,
    error                  text,
    created_at             timestamptz NOT NULL DEFAULT now(),
    started_at             timestamptz,
    finished_at            timestamptz
);

CREATE TABLE job_steps (
    id          bigserial PRIMARY KEY,
    job_id      uuid NOT NULL REFERENCES data_ingestion_jobs (id) ON DELETE CASCADE,
    name        text NOT NULL,
    status      text NOT NULL,
    started_at  timestamptz,
    finished_at timestamptz,
    message     text
);

CREATE TABLE validation_findings (
    id       bigserial PRIMARY KEY,
    job_id   uuid NOT NULL REFERENCES data_ingestion_jobs (id) ON DELETE CASCADE,
    severity finding_severity NOT NULL,
    code     text NOT NULL,
    message  text NOT NULL,
    variable text
);

CREATE TABLE models (
    id   serial PRIMARY KEY,
    name text UNIQUE NOT NULL,
    kind text NOT NULL                                 -- anomaly_detector | tracker | downscaler | risk
);

CREATE TABLE model_runs (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    model_id            integer NOT NULL REFERENCES models (id),
    version             text NOT NULL,
    run_type            text NOT NULL CHECK (run_type IN ('training', 'evaluation', 'inference')),
    status              text NOT NULL DEFAULT 'experimental' CHECK (status IN ('experimental', 'candidate', 'recommended', 'baseline', 'retired')),
    architecture        text,
    training_dataset_id text REFERENCES datasets (id),
    training_period     tstzrange,
    parameters          bigint,
    checkpoint_uri      text,
    checkpoint_sha256   char(64),
    seed                integer,
    hyperparameters     jsonb NOT NULL DEFAULT '{}'::jsonb,
    loss_weights        jsonb NOT NULL DEFAULT '{}'::jsonb,
    device              text,
    git_sha             text,
    config_hash         text,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE model_metrics (
    id           bigserial PRIMARY KEY,
    model_run_id uuid NOT NULL REFERENCES model_runs (id) ON DELETE CASCADE,
    name         text NOT NULL,
    value        double precision NOT NULL,
    ci_low       double precision,
    ci_high      double precision,
    split        text NOT NULL DEFAULT 'test',
    n            integer
);

CREATE TABLE forecast_runs (
    id                  text PRIMARY KEY,
    dataset_id          text REFERENCES datasets (id),
    source_id           integer REFERENCES data_sources (id),
    data_kind           data_kind NOT NULL,
    initialization_time timestamptz NOT NULL,                  -- UTC
    n_members           integer NOT NULL DEFAULT 1 CHECK (n_members >= 1),
    lead_hours          integer[] NOT NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (dataset_id, initialization_time)
);

CREATE TABLE forecast_members (
    id              bigserial PRIMARY KEY,
    forecast_run_id text NOT NULL REFERENCES forecast_runs (id) ON DELETE CASCADE,
    member          integer NOT NULL CHECK (member >= 0),      -- 0 = control
    storage_key     text,
    UNIQUE (forecast_run_id, member)
);

CREATE TABLE weather_events (
    id               uuid PRIMARY KEY,
    event_type       event_type NOT NULL,
    status           text NOT NULL,
    severity         severity NOT NULL,
    data_kind        data_kind NOT NULL,
    first_valid_time timestamptz NOT NULL,
    last_valid_time  timestamptz NOT NULL,
    peak_intensity   double precision,
    peak_unit        text,
    peak_lead_hours  integer,
    max_area_km2     double precision,
    probability      real CHECK (probability BETWEEN 0 AND 1),
    confidence       confidence_class,
    risk_score       real CHECK (risk_score BETWEEN 0 AND 1),
    footprint        geometry(MultiPolygon, 4326),
    centroid         geometry(Point, 4326),
    forecast_run_id  text REFERENCES forecast_runs (id),
    dataset_id       text REFERENCES datasets (id),
    model_run_id     uuid REFERENCES model_runs (id),
    provenance       jsonb NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),
    CHECK (last_valid_time >= first_valid_time)
);

CREATE TABLE event_tracks (
    id                    bigserial PRIMARY KEY,
    event_id              uuid NOT NULL REFERENCES weather_events (id) ON DELETE CASCADE,
    member                integer NOT NULL DEFAULT 0,          -- 0 = control
    valid_time            timestamptz NOT NULL,
    lead_hours            integer NOT NULL,
    centroid              geometry(Point, 4326) NOT NULL,
    footprint             geometry(MultiPolygon, 4326),
    radius_km             real,
    area_km2              double precision,
    intensity             double precision,
    speed_kmh             real,
    bearing_deg           real CHECK (bearing_deg IS NULL OR bearing_deg >= 0 AND bearing_deg < 360),
    probability           real CHECK (probability IS NULL OR probability BETWEEN 0 AND 1),
    uncertainty_radius_km real,
    track_source          track_source NOT NULL,
    observed              boolean NOT NULL DEFAULT true,
    UNIQUE (event_id, member, valid_time, track_source)
);

CREATE TABLE anomaly_regions (
    id                 bigserial PRIMARY KEY,
    forecast_run_id    text NOT NULL REFERENCES forecast_runs (id) ON DELETE CASCADE,
    valid_time         timestamptz NOT NULL,
    variable           text NOT NULL REFERENCES weather_variables (name),
    detector           text NOT NULL,
    detector_config_hash text,
    geom               geometry(MultiPolygon, 4326) NOT NULL,
    centroid           geometry(Point, 4326) NOT NULL,
    area_km2           double precision NOT NULL CHECK (area_km2 >= 0),
    max_intensity      double precision,
    mean_intensity     double precision,
    perimeter_km       double precision,
    confidence         real CHECK (confidence BETWEEN 0 AND 1)
);

CREATE TABLE impact_geometries (
    id         bigserial PRIMARY KEY,
    event_id   uuid NOT NULL REFERENCES weather_events (id) ON DELETE CASCADE,
    kind       geometry_kind NOT NULL,
    valid_time timestamptz NOT NULL,
    geom       geometry(MultiPolygon, 4326) NOT NULL,
    params     jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (event_id, kind, valid_time)
);

CREATE TABLE downscaled_products (
    id                bigserial PRIMARY KEY,
    event_id          uuid REFERENCES weather_events (id) ON DELETE CASCADE,
    dataset_id        text REFERENCES datasets (id),
    model_run_id      uuid REFERENCES model_runs (id),
    method            text NOT NULL,
    valid_time        timestamptz NOT NULL,
    storage_key       text NOT NULL,
    src_resolution_km real,
    dst_resolution_km real,
    n_samples         integer NOT NULL DEFAULT 1 CHECK (n_samples >= 1),
    physics_report    jsonb,
    data_kind         data_kind NOT NULL
);

CREATE TABLE geographic_regions (
    id               text PRIMARY KEY,
    level            region_level NOT NULL,
    code             text,
    name             text NOT NULL,
    geom             geometry(MultiPolygon, 4326) NOT NULL,
    boundary_source  text NOT NULL,           -- must be recorded: boundaries are legally sensitive
    boundary_version text
);

CREATE TABLE alerts (
    id              uuid PRIMARY KEY,
    event_id        uuid NOT NULL REFERENCES weather_events (id) ON DELETE CASCADE,
    event_type      event_type NOT NULL,
    severity        severity NOT NULL,
    forecast_window tstzrange NOT NULL,
    probability     real CHECK (probability BETWEEN 0 AND 1),
    confidence      confidence_class,
    uncertainty     jsonb NOT NULL DEFAULT '{}'::jsonb,
    source          text NOT NULL,
    model_version   text NOT NULL,
    status          text NOT NULL,
    data_kind       data_kind NOT NULL,
    risk_polygon    geometry(MultiPolygon, 4326),
    disclaimer      text NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE alert_regions (
    alert_id           uuid NOT NULL REFERENCES alerts (id) ON DELETE CASCADE,
    region_id          text NOT NULL REFERENCES geographic_regions (id),
    polygon_kind       geometry_kind NOT NULL,
    intersect_area_km2 double precision NOT NULL,
    fraction_of_region real,
    PRIMARY KEY (alert_id, region_id, polygon_kind)
);

CREATE TABLE users (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name           text UNIQUE NOT NULL,
    role           user_role NOT NULL DEFAULT 'viewer',
    api_key_sha256 char(64) UNIQUE,              -- digest only; raw keys are never stored
    is_active      boolean NOT NULL DEFAULT true,
    created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE audit_logs (
    id         bigserial PRIMARY KEY,
    ts         timestamptz NOT NULL DEFAULT now(),
    actor      text NOT NULL,
    action     text NOT NULL,
    outcome    text NOT NULL,
    request_id text,
    details    jsonb NOT NULL DEFAULT '{}'::jsonb
);

-- audit_logs is append-only: updates and deletes are rejected for every role.
CREATE FUNCTION audit_logs_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit_logs is append-only';
END;
$$;
CREATE TRIGGER audit_logs_no_update BEFORE UPDATE OR DELETE ON audit_logs
    FOR EACH ROW EXECUTE FUNCTION audit_logs_immutable();
CREATE TRIGGER audit_logs_no_truncate BEFORE TRUNCATE ON audit_logs
    FOR EACH STATEMENT EXECUTE FUNCTION audit_logs_immutable();

-- ---------------------------------------------------------------- indexes
CREATE INDEX idx_events_type_sev_time ON weather_events (event_type, severity, last_valid_time DESC);
CREATE INDEX idx_events_event_type    ON weather_events (event_type);
CREATE INDEX idx_events_severity      ON weather_events (severity);
CREATE INDEX idx_events_first_valid   ON weather_events (first_valid_time);
CREATE INDEX idx_events_last_valid    ON weather_events (last_valid_time);
CREATE INDEX idx_events_run            ON weather_events (forecast_run_id);
CREATE INDEX idx_events_dataset        ON weather_events (dataset_id);
CREATE INDEX gist_events_footprint     ON weather_events USING gist (footprint);
CREATE INDEX gist_events_centroid      ON weather_events USING gist (centroid);

CREATE INDEX idx_tracks_event_time     ON event_tracks (event_id, valid_time);
CREATE INDEX gist_tracks_centroid      ON event_tracks USING gist (centroid);
CREATE INDEX gist_tracks_footprint     ON event_tracks USING gist (footprint);

CREATE INDEX idx_regions_run_time      ON anomaly_regions (forecast_run_id, valid_time);
CREATE INDEX gist_anomaly_geom         ON anomaly_regions USING gist (geom);
CREATE INDEX gist_impact_geom          ON impact_geometries USING gist (geom);
CREATE INDEX idx_impact_event          ON impact_geometries (event_id, kind);
CREATE INDEX gist_georegions_geom      ON geographic_regions USING gist (geom);
CREATE INDEX idx_georegions_level      ON geographic_regions (level, code);
CREATE INDEX gist_dataset_extent       ON datasets USING gist (geographic_extent);
CREATE INDEX idx_datasets_source       ON datasets (source_id);

CREATE INDEX idx_alerts_event          ON alerts (event_id);
CREATE INDEX idx_alerts_sev_created    ON alerts (severity, created_at DESC);
CREATE INDEX gist_alerts_window        ON alerts USING gist (forecast_window);
CREATE INDEX gist_alerts_polygon       ON alerts USING gist (risk_polygon);

CREATE INDEX idx_forecast_members_run  ON forecast_members (forecast_run_id);
CREATE INDEX idx_jobs_status           ON data_ingestion_jobs (status, created_at DESC);
CREATE INDEX idx_metrics_run           ON model_metrics (model_run_id);
CREATE INDEX idx_audit_ts              ON audit_logs (ts DESC);
CREATE INDEX idx_audit_actor_action    ON audit_logs (actor, action);

COMMIT;
