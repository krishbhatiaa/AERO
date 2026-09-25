"""Standalone Redis-backed worker process for the extreme-weather-ai pipeline.

Pulls jobs from ``ewai:jobs`` (FIFO BRPOP), executes them, and publishes progress
events to ``ewai:events`` via Redis pub/sub.  Job state lives in ``ewai:job:{id}``
keys with a TTL so stale records are automatically evicted.
"""
from __future__ import annotations

import json
import logging
import signal
import sys
import time
import traceback
import uuid
from datetime import UTC, datetime
from typing import Any

log = logging.getLogger("ewai.worker")

QUEUE_KEY = "ewai:jobs"
JOB_KEY_PREFIX = "ewai:job:"
EVENT_CHANNEL = "ewai:events"
MAX_RETRIES = 3
BASE_BACKOFF = 1.0
JOB_TTL = 86400
QUEUE_BLOCK_TIMEOUT = 5


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _job_key(job_id: str) -> str:
    return f"{JOB_KEY_PREFIX}{job_id}"


class _Shutdown:
    def __init__(self) -> None:
        self.flag = False

    def trigger(self, *_: Any) -> None:
        log.info("shutdown signal received")
        self.flag = True


def _get_runner(job_type: str):
    if job_type == "ingest":
        return _run_ingest
    if job_type in ("prediction", "downscale", "demo"):
        return _run_prediction
    raise ValueError(f"unknown job type: {job_type}")


def _run_ingest(params: dict[str, Any], progress: Any, redis_client: Any) -> dict[str, Any]:
    from data_pipeline.adapters.base import DatasetRequest
    from data_pipeline.adapters.sources import ADAPTERS
    from data_pipeline.ingestion.pipeline import run_ingestion
    from data_pipeline.validation.checks import ValidationSchema

    source = str(params.get("source", "era5")).lower()
    dataset_id = str(params.get("dataset_id", f"{source}-ingest"))
    progress("ingest_start", 0.05)

    adapter = ADAPTERS[source]()
    vm = adapter.variable_map()
    schema = ValidationSchema(required_vars=tuple(vm), expected_units={k: v["from_units"] for k, v in vm.items() if "from_units" in v})
    req = DatasetRequest()

    ing = run_ingestion(adapter, req, None, schema, dataset_id)
    progress("ingest_done", 1.0)

    if ing.status != "SUCCEEDED":
        raise RuntimeError(ing.error or "ingestion failed")

    return {
        "ingestion_status": str(ing.status),
        "storage_key": ing.storage_key,
        "dataset_id": dataset_id,
        "validation_ok": bool((ing.validation or {}).get("ok", False)),
    }


def _run_prediction(params: dict[str, Any], progress: Any, redis_client: Any) -> dict[str, Any]:
    from ml.pipeline.real import run_real_pipeline

    result = run_real_pipeline(progress=progress)
    return {
        "event_id": result.provenance.dataset_id,
        "config_digest": result.config_digest,
        "risk_category": result.risk.category,
        "risk_score": result.risk.score,
    }


def _publish_event(redis_client: Any, event_type: str, payload: dict[str, Any]) -> None:
    msg = {"type": event_type, "ts_utc": _now_iso(), "payload": payload}
    try:
        redis_client.publish(EVENT_CHANNEL, json.dumps(msg, default=str))
    except Exception:  # noqa: BLE001
        log.warning("failed to publish event", extra={"event_type": event_type})


def _update_job(redis_client: Any, job_id: str, updates: dict[str, Any], ttl: int = JOB_TTL) -> None:
    key = _job_key(job_id)
    try:
        existing = redis_client.get(key)
        data = json.loads(existing) if existing else {}
        data.update(updates)
        redis_client.set(key, json.dumps(data, default=str), ex=ttl)
    except Exception:  # noqa: BLE001
        log.warning("failed to update job state", extra={"job_id": job_id})


def process_job(redis_client: Any, raw: bytes) -> None:
    try:
        job = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        log.error("invalid job payload", extra={"error": str(exc)})
        return

    job_id = job.get("job_id", uuid.uuid4().hex)
    job_type = job.get("type", "unknown")
    params = job.get("params", {})
    request_id = job.get("request_id", "-")
    retries = int(job.get("retries", 0))

    log.info("job received", extra={"job_id": job_id, "type": job_type, "retries": retries})
    _update_job(redis_client, job_id, {"status": "RUNNING", "started_at": _now_iso(), "type": job_type, "retries": retries})

    def progress(step: str, fraction: float) -> None:
        frac = round(float(fraction), 3)
        _update_job(redis_client, job_id, {"current_step": step, "progress": frac})
        _publish_event(redis_client, "job.progress", {"job_id": job_id, "step": step, "fraction": frac})

    _publish_event(redis_client, "job.started", {"job_id": job_id, "type": job_type})

    runner = _get_runner(job_type)
    try:
        result = runner(params, progress, redis_client)
        _update_job(redis_client, job_id, {
            "status": "SUCCEEDED",
            "finished_at": _now_iso(),
            "result": result,
        })
        _publish_event(redis_client, "job.finished", {"job_id": job_id, "status": "SUCCEEDED"})
        log.info("job succeeded", extra={"job_id": job_id, "type": job_type})
    except Exception as exc:  # noqa: BLE001
        log.error("job failed", extra={"job_id": job_id, "type": job_type, "exc_type": type(exc).__name__}, exc_info=True)

        if retries < MAX_RETRIES:
            backoff = BASE_BACKOFF * (2 ** retries)
            retry_job = {
                **job,
                "job_id": job_id,
                "retries": retries + 1,
            }
            _update_job(redis_client, job_id, {
                "status": "RETRYING",
                "error": str(exc),
                "retries": retries + 1,
                "next_retry_at": _now_iso(),
            })
            _publish_event(redis_client, "job.retrying", {"job_id": job_id, "retries": retries + 1, "backoff_s": backoff})
            try:
                import redis
                retry_client = redis.Redis.from_url(redis_client.connection_pool.connection_kwargs.get("url", ""), socket_connect_timeout=1)
                retry_client.lpush(QUEUE_KEY, json.dumps(retry_job, default=str))
            except Exception:  # noqa: BLE001
                log.error("failed to enqueue retry", extra={"job_id": job_id})
        else:
            _update_job(redis_client, job_id, {
                "status": "FAILED",
                "finished_at": _now_iso(),
                "error": str(exc),
            })
            _publish_event(redis_client, "job.finished", {"job_id": job_id, "status": "FAILED"})
            log.error("job failed permanently", extra={"job_id": job_id, "type": job_type, "retries": retries})


def run_worker(redis_url: str) -> None:
    import redis as redis_lib

    log.info("starting worker", extra={"redis_url": redis_url})
    client = redis_lib.Redis.from_url(redis_url, socket_connect_timeout=5, socket_timeout=5)

    shutdown = _Shutdown()
    signal.signal(signal.SIGTERM, shutdown.trigger)
    signal.signal(signal.SIGINT, shutdown.trigger)

    try:
        client.ping()
    except Exception as exc:  # noqa: BLE001
        log.error("cannot connect to Redis", extra={"error": str(exc)})
        sys.exit(1)

    log.info("worker connected, listening on queue", extra={"queue": QUEUE_KEY})

    while not shutdown.flag:
        try:
            result = client.brpop(QUEUE_KEY, timeout=QUEUE_BLOCK_TIMEOUT)
            if result is None:
                continue
            _, raw = result
            process_job(client, raw)
        except redis_lib.exceptions.ConnectionError:
            log.warning("redis connection lost, retrying in 5s")
            time.sleep(5)
        except Exception:  # noqa: BLE001
            log.error("unexpected worker error", exc_info=True)
            time.sleep(1)

    log.info("worker shutting down")
    try:
        client.close()
    except Exception:  # noqa: BLE001
        pass
