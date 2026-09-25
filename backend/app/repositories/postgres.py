"""Concrete repository implementations backed by asyncpg (PostgreSQL + PostGIS).

Each repository maps between Python dicts and SQL rows.  Geometry columns use WKB
(Well-Known Binary) via asyncpg's PostGIS integration.  All queries are parameterised
to prevent SQL injection.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import asyncpg

log = logging.getLogger("ewai.repositories")


def _row_to_dict(row: asyncpg.Record | None) -> dict[str, Any] | None:
    if row is None:
        return None
    d = dict(row)
    for k, v in d.items():
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat()
        elif isinstance(v, memoryview):
            d[k] = bytes(v).hex()
        elif isinstance(v, dict):
            pass
        elif isinstance(v, list):
            pass
    return d


def _rows_to_dicts(rows: list[asyncpg.Record]) -> list[dict[str, Any]]:
    return [_row_to_dict(r) for r in rows]


class EventRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get(self, id: str) -> dict | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM weather_events WHERE id = $1", id)
            return _row_to_dict(row)

    async def create(self, data: dict) -> str:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO weather_events
                   (id, event_type, status, severity, data_kind, first_valid_time, last_valid_time,
                    peak_intensity, peak_unit, peak_lead_hours, max_area_km2, probability, confidence,
                    risk_score, forecast_run_id, dataset_id, model_run_id, provenance)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18)""",
                data["id"], data["event_type"], data["status"], data["severity"], data["data_kind"],
                data["first_valid_time"], data["last_valid_time"],
                data.get("peak_intensity"), data.get("peak_unit"), data.get("peak_lead_hours"),
                data.get("max_area_km2"), data.get("probability"), data.get("confidence"),
                data.get("risk_score"), data.get("forecast_run_id"), data.get("dataset_id"),
                data.get("model_run_id"), json.dumps(data.get("provenance", {})),
            )
            return data["id"]

    async def update(self, id: str, data: dict) -> bool:
        sets, vals, idx = [], [], 1
        for k, v in data.items():
            if k == "id":
                continue
            idx += 1
            if isinstance(v, dict):
                sets.append(f"{k} = ${idx}::jsonb")
                vals.append(json.dumps(v))
            else:
                sets.append(f"{k} = ${idx}")
                vals.append(v)
        if not sets:
            return False
        vals.append(id)
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                f"UPDATE weather_events SET {', '.join(sets)} WHERE id = ${idx + 1}", *vals
            )
            return result == "UPDATE 1"

    async def delete(self, id: str) -> bool:
        async with self._pool.acquire() as conn:
            result = await conn.execute("DELETE FROM weather_events WHERE id = $1", id)
            return result == "DELETE 1"

    async def list(self, limit: int = 100, offset: int = 0) -> list[dict]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM weather_events ORDER BY created_at DESC LIMIT $1 OFFSET $2",
                limit, offset,
            )
            return _rows_to_dicts(rows)


class ForecastRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get(self, id: str) -> dict | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM forecast_runs WHERE id = $1", id)
            return _row_to_dict(row)

    async def create(self, data: dict) -> str:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO forecast_runs
                   (id, dataset_id, source_id, data_kind, initialization_time, n_members, lead_hours)
                   VALUES ($1,$2,$3,$4,$5,$6,$7)""",
                data["id"], data.get("dataset_id"), data.get("source_id"), data["data_kind"],
                data["initialization_time"], data.get("n_members", 1), data.get("lead_hours", []),
            )
            if "members" in data:
                for m in data["members"]:
                    await conn.execute(
                        "INSERT INTO forecast_members (forecast_run_id, member, storage_key) VALUES ($1,$2,$3)",
                        data["id"], m.get("member", 0), m.get("storage_key"),
                    )
            return data["id"]

    async def update(self, id: str, data: dict) -> bool:
        sets, vals, idx = [], [], 1
        for k, v in data.items():
            if k in ("id", "members"):
                continue
            idx += 1
            if isinstance(v, (dict, list)):
                sets.append(f"{k} = ${idx}::jsonb")
                vals.append(json.dumps(v))
            else:
                sets.append(f"{k} = ${idx}")
                vals.append(v)
        if not sets:
            return False
        vals.append(id)
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                f"UPDATE forecast_runs SET {', '.join(sets)} WHERE id = ${idx + 1}", *vals
            )
            return result == "UPDATE 1"

    async def delete(self, id: str) -> bool:
        async with self._pool.acquire() as conn:
            result = await conn.execute("DELETE FROM forecast_runs WHERE id = $1", id)
            return result == "DELETE 1"

    async def list(self, limit: int = 100, offset: int = 0) -> list[dict]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM forecast_runs ORDER BY created_at DESC LIMIT $1 OFFSET $2",
                limit, offset,
            )
            return _rows_to_dicts(rows)

    async def get_members(self, forecast_run_id: str) -> list[dict]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM forecast_members WHERE forecast_run_id = $1 ORDER BY member",
                forecast_run_id,
            )
            return _rows_to_dicts(rows)


class AlertRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get(self, id: str) -> dict | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM alerts WHERE id = $1", id)
            return _row_to_dict(row)

    async def create(self, data: dict) -> str:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO alerts
                   (id, event_id, event_type, severity, forecast_window, probability, confidence,
                    uncertainty, source, model_version, status, data_kind, disclaimer)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)""",
                data["id"], data["event_id"], data["event_type"], data["severity"],
                data.get("forecast_window"), data.get("probability"), data.get("confidence"),
                json.dumps(data.get("uncertainty", {})), data["source"], data["model_version"],
                data["status"], data["data_kind"], data.get("disclaimer", ""),
            )
            if "regions" in data:
                for r in data["regions"]:
                    await conn.execute(
                        """INSERT INTO alert_regions
                           (alert_id, region_id, polygon_kind, intersect_area_km2, fraction_of_region)
                           VALUES ($1,$2,$3,$4,$5)""",
                        data["id"], r["region_id"], r["polygon_kind"],
                        r.get("intersect_area_km2", 0), r.get("fraction_of_region"),
                    )
            return data["id"]

    async def update(self, id: str, data: dict) -> bool:
        sets, vals, idx = [], [], 1
        for k, v in data.items():
            if k in ("id", "regions"):
                continue
            idx += 1
            if isinstance(v, dict):
                sets.append(f"{k} = ${idx}::jsonb")
                vals.append(json.dumps(v))
            else:
                sets.append(f"{k} = ${idx}")
                vals.append(v)
        if not sets:
            return False
        vals.append(id)
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                f"UPDATE alerts SET {', '.join(sets)} WHERE id = ${idx + 1}", *vals
            )
            return result == "UPDATE 1"

    async def delete(self, id: str) -> bool:
        async with self._pool.acquire() as conn:
            result = await conn.execute("DELETE FROM alerts WHERE id = $1", id)
            return result == "DELETE 1"

    async def list(self, limit: int = 100, offset: int = 0) -> list[dict]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM alerts ORDER BY created_at DESC LIMIT $1 OFFSET $2",
                limit, offset,
            )
            return _rows_to_dicts(rows)


class DatasetRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get(self, id: str) -> dict | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM datasets WHERE id = $1", id)
            return _row_to_dict(row)

    async def create(self, data: dict) -> str:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO datasets
                   (id, source_id, name, data_kind, storage_key, checksum_sha256, grid, dimensions,
                    temporal_start, temporal_end, metadata)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)""",
                data["id"], data.get("source_id"), data["name"], data["data_kind"],
                data.get("storage_key"), data.get("checksum_sha256"),
                json.dumps(data.get("grid")) if data.get("grid") else None,
                json.dumps(data.get("dimensions")) if data.get("dimensions") else None,
                data.get("temporal_start"), data.get("temporal_end"),
                json.dumps(data.get("metadata", {})),
            )
            if "variables" in data:
                for var in data["variables"]:
                    await conn.execute(
                        """INSERT INTO dataset_variables (dataset_id, variable, source_units)
                           VALUES ($1,$2,$3)""",
                        data["id"], var["name"], var.get("source_units"),
                    )
            return data["id"]

    async def update(self, id: str, data: dict) -> bool:
        sets, vals, idx = [], [], 1
        for k, v in data.items():
            if k in ("id", "variables"):
                continue
            idx += 1
            if isinstance(v, (dict, list)):
                sets.append(f"{k} = ${idx}::jsonb")
                vals.append(json.dumps(v))
            else:
                sets.append(f"{k} = ${idx}")
                vals.append(v)
        if not sets:
            return False
        vals.append(id)
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                f"UPDATE datasets SET {', '.join(sets)} WHERE id = ${idx + 1}", *vals
            )
            return result == "UPDATE 1"

    async def delete(self, id: str) -> bool:
        async with self._pool.acquire() as conn:
            result = await conn.execute("DELETE FROM datasets WHERE id = $1", id)
            return result == "DELETE 1"

    async def list(self, limit: int = 100, offset: int = 0) -> list[dict]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM datasets ORDER BY created_at DESC LIMIT $1 OFFSET $2",
                limit, offset,
            )
            return _rows_to_dicts(rows)


class JobRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get(self, id: str) -> dict | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM data_ingestion_jobs WHERE id = $1", id)
            return _row_to_dict(row)

    async def create(self, data: dict) -> str:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO data_ingestion_jobs
                   (id, source_id, dataset_id, status, files, checksum_sha256, preprocess_config_hash)
                   VALUES ($1,$2,$3,$4,$5,$6,$7)""",
                data["id"], data.get("source_id"), data.get("dataset_id"),
                data.get("status", "PENDING"),
                json.dumps(data.get("files", [])),
                data.get("checksum_sha256"), data.get("preprocess_config_hash"),
            )
            return data["id"]

    async def update(self, id: str, data: dict) -> bool:
        sets, vals, idx = [], [], 1
        for k, v in data.items():
            if k == "id":
                continue
            idx += 1
            if isinstance(v, (dict, list)):
                sets.append(f"{k} = ${idx}::jsonb")
                vals.append(json.dumps(v))
            else:
                sets.append(f"{k} = ${idx}")
                vals.append(v)
        if not sets:
            return False
        vals.append(id)
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                f"UPDATE data_ingestion_jobs SET {', '.join(sets)} WHERE id = ${idx + 1}", *vals
            )
            return result == "UPDATE 1"

    async def delete(self, id: str) -> bool:
        async with self._pool.acquire() as conn:
            result = await conn.execute("DELETE FROM data_ingestion_jobs WHERE id = $1", id)
            return result == "DELETE 1"

    async def list(self, limit: int = 100, offset: int = 0) -> list[dict]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM data_ingestion_jobs ORDER BY created_at DESC LIMIT $1 OFFSET $2",
                limit, offset,
            )
            return _rows_to_dicts(rows)

    async def add_step(self, job_id: str, name: str, status: str, message: str | None = None) -> int:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO job_steps (job_id, name, status, message)
                   VALUES ($1,$2,$3,$4) RETURNING id""",
                job_id, name, status, message,
            )
            return row["id"]

    async def add_finding(self, job_id: str, severity: str, code: str, message: str, variable: str | None = None) -> int:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO validation_findings (job_id, severity, code, message, variable)
                   VALUES ($1,$2,$3,$4,$5) RETURNING id""",
                job_id, severity, code, message, variable,
            )
            return row["id"]


class ModelRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get(self, id: str) -> dict | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM models WHERE id = $1", int(id) if id.isdigit() else id)
            return _row_to_dict(row)

    async def create(self, data: dict) -> str:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO models (name, kind) VALUES ($1,$2) RETURNING id",
                data["name"], data["kind"],
            )
            return str(row["id"])

    async def update(self, id: str, data: dict) -> bool:
        sets, vals, idx = [], [], 1
        for k, v in data.items():
            if k == "id":
                continue
            idx += 1
            sets.append(f"{k} = ${idx}")
            vals.append(v)
        if not sets:
            return False
        vals.append(int(id) if id.isdigit() else id)
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                f"UPDATE models SET {', '.join(sets)} WHERE id = ${idx + 1}", *vals
            )
            return result == "UPDATE 1"

    async def delete(self, id: str) -> bool:
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM models WHERE id = $1", int(id) if id.isdigit() else id
            )
            return result == "DELETE 1"

    async def list(self, limit: int = 100, offset: int = 0) -> list[dict]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM models ORDER BY id LIMIT $1 OFFSET $2", limit, offset
            )
            return _rows_to_dicts(rows)

    async def create_run(self, data: dict) -> str:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO model_runs
                   (model_id, version, run_type, status, architecture, training_dataset_id,
                    training_period, parameters, checkpoint_uri, checkpoint_sha256,
                    seed, hyperparameters, loss_weights, device, git_sha, config_hash)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
                   RETURNING id""",
                data["model_id"], data["version"], data["run_type"],
                data.get("status", "experimental"), data.get("architecture"),
                data.get("training_dataset_id"), data.get("training_period"),
                data.get("parameters"), data.get("checkpoint_uri"),
                data.get("checkpoint_sha256"), data.get("seed"),
                json.dumps(data.get("hyperparameters", {})),
                json.dumps(data.get("loss_weights", {})),
                data.get("device"), data.get("git_sha"), data.get("config_hash"),
            )
            return str(row["id"])

    async def add_metric(self, model_run_id: str, name: str, value: float,
                         ci_low: float | None = None, ci_high: float | None = None,
                         split: str = "test", n: int | None = None) -> int:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO model_metrics (model_run_id, name, value, ci_low, ci_high, split, n)
                   VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id""",
                model_run_id, name, value, ci_low, ci_high, split, n,
            )
            return row["id"]


class AuditRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get(self, id: str) -> dict | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM audit_logs WHERE id = $1", int(id) if id.isdigit() else id)
            return _row_to_dict(row)

    async def create(self, data: dict) -> str:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO audit_logs (actor, action, outcome, request_id, details)
                   VALUES ($1,$2,$3,$4,$5) RETURNING id""",
                data["actor"], data["action"], data.get("outcome", "ok"),
                data.get("request_id"), json.dumps(data.get("details", {})),
            )
            return str(row["id"])

    async def update(self, id: str, data: dict) -> bool:
        raise NotImplementedError("audit_logs is append-only")

    async def delete(self, id: str) -> bool:
        raise NotImplementedError("audit_logs is append-only")

    async def list(self, limit: int = 100, offset: int = 0) -> list[dict]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM audit_logs ORDER BY ts DESC LIMIT $1 OFFSET $2",
                limit, offset,
            )
            return _rows_to_dicts(rows)
