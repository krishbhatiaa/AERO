-- Additional job tracking tables for ML training and pipeline runs.
BEGIN;

CREATE TYPE ml_job_status AS ENUM ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED');

CREATE TABLE ml_training_jobs (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    model_id        integer REFERENCES models (id),
    name            text NOT NULL,
    status          ml_job_status NOT NULL DEFAULT 'QUEUED',
    dataset_id      text REFERENCES datasets (id),
    config          jsonb NOT NULL DEFAULT '{}'::jsonb,
    hyperparameters jsonb NOT NULL DEFAULT '{}'::jsonb,
    seed            integer,
    git_sha         text,
    error           text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    started_at      timestamptz,
    finished_at     timestamptz,
    created_by      text
);

CREATE TABLE ml_training_metrics (
    id              bigserial PRIMARY KEY,
    job_id          uuid NOT NULL REFERENCES ml_training_jobs (id) ON DELETE CASCADE,
    epoch           integer NOT NULL,
    metric_name     text NOT NULL,
    metric_value    double precision NOT NULL,
    learning_rate   double precision,
    recorded_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TYPE pipeline_run_status AS ENUM ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'PARTIAL');

CREATE TABLE pipeline_runs (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_name   text NOT NULL,
    status          pipeline_run_status NOT NULL DEFAULT 'PENDING',
    config          jsonb NOT NULL DEFAULT '{}'::jsonb,
    input_refs      jsonb NOT NULL DEFAULT '[]'::jsonb,
    output_refs     jsonb NOT NULL DEFAULT '[]'::jsonb,
    error           text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    started_at      timestamptz,
    finished_at     timestamptz,
    duration_ms     integer,
    created_by      text
);

CREATE INDEX idx_ml_jobs_status      ON ml_training_jobs (status, created_at DESC);
CREATE INDEX idx_ml_jobs_model       ON ml_training_jobs (model_id);
CREATE INDEX idx_ml_metrics_job      ON ml_training_metrics (job_id, epoch);
CREATE INDEX idx_pipeline_status     ON pipeline_runs (status, created_at DESC);
CREATE INDEX idx_pipeline_name       ON pipeline_runs (pipeline_name);

COMMIT;
