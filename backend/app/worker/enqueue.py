"""Job submission and status helpers for the Redis-backed worker queue."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from app.worker.worker import JOB_KEY_PREFIX, JOB_TTL, QUEUE_KEY

log = logging.getLogger("ewai.worker.enqueue")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def submit_job(
    redis_url: str,
    job_type: str,
    params: dict[str, Any],
    created_by: str = "system",
    request_id: str = "-",
) -> str:
    import redis as redis_lib

    client = redis_lib.Redis.from_url(redis_url, socket_connect_timeout=5, socket_timeout=5)
    try:
        job_id = uuid.uuid4().hex
        job = {
            "job_id": job_id,
            "type": job_type,
            "params": params,
            "created_by": created_by,
            "request_id": request_id,
            "retries": 0,
            "created_at": _now_iso(),
        }
        client.lpush(QUEUE_KEY, json.dumps(job, default=str))
        client.set(f"{JOB_KEY_PREFIX}{job_id}", json.dumps({
            "job_id": job_id,
            "type": job_type,
            "status": "PENDING",
            "params": params,
            "created_by": created_by,
            "request_id": request_id,
            "retries": 0,
            "created_at": job["created_at"],
        }, default=str), ex=JOB_TTL)
        log.info("job submitted", extra={"job_id": job_id, "type": job_type})
        return job_id
    finally:
        try:
            client.close()
        except Exception:  # noqa: BLE001
            pass


def get_job_status(redis_url: str, job_id: str) -> dict[str, Any] | None:
    import redis as redis_lib

    client = redis_lib.Redis.from_url(redis_url, socket_connect_timeout=5, socket_timeout=5)
    try:
        raw = client.get(f"{JOB_KEY_PREFIX}{job_id}")
        if raw is None:
            return None
        return json.loads(raw)
    finally:
        try:
            client.close()
        except Exception:  # noqa: BLE001
            pass


def list_jobs(redis_url: str, limit: int = 50) -> list[dict[str, Any]]:
    import redis as redis_lib

    client = redis_lib.Redis.from_url(redis_url, socket_connect_timeout=5, socket_timeout=5)
    try:
        keys: list[bytes] = []
        cursor = 0
        while True:
            cursor, batch = client.scan(cursor=cursor, match=f"{JOB_KEY_PREFIX}*", count=100)
            keys.extend(batch)
            if cursor == 0:
                break
        jobs: list[dict[str, Any]] = []
        for key in keys:
            raw = client.get(key)
            if raw is not None:
                try:
                    jobs.append(json.loads(raw))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
        jobs.sort(key=lambda j: j.get("created_at", ""), reverse=True)
        return jobs[:limit]
    finally:
        try:
            client.close()
        except Exception:  # noqa: BLE001
            pass
