"""In-process job manager (thread pool). Job records are always driven to a terminal state.

Celery/Redis workers are the planned production executor (Batchsize.md); this keeps the demo self-contained and
gives the API/WebSocket the same job model.
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from threading import Lock
from typing import Any

from app.core.logging import job_id_var

log = logging.getLogger("app.jobs")
JOB_TYPES = ("demo", "prediction", "ingest")


class JobFailure(RuntimeError):
    """Raised by a runner with a message that is safe to show to API clients (no paths, secrets or stack traces)."""


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass
class Job:
    id: str
    type: str
    params: dict[str, Any]
    created_by: str
    request_id: str
    status: str = "PENDING"
    created_at: str = field(default_factory=_now)
    started_at: str | None = None
    finished_at: str | None = None
    progress: float = 0.0
    current_step: str | None = None
    steps: list[dict[str, Any]] = field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


Runner = Callable[[Job, Callable[[str, float], None]], dict[str, Any]]


class JobManager:
    def __init__(self, on_event: Callable[[str, str, dict[str, Any]], None] | None = None, max_history: int = 200) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = Lock()
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ewai-job")
        self._emit = on_event or (lambda *_: None)
        self._max = max_history

    def submit(self, type_: str, params: dict[str, Any], runner: Runner, created_by: str, request_id: str) -> Job:
        job = Job(uuid.uuid4().hex, type_, params, created_by, request_id)
        with self._lock:
            self._jobs[job.id] = job
            for old in list(self._jobs)[: max(0, len(self._jobs) - self._max)]:
                self._jobs.pop(old, None)
        self._pool.submit(self._run, job, runner)
        return job

    def _run(self, job: Job, runner: Runner) -> None:
        job_id_var.set(job.id)
        job.status, job.started_at = "RUNNING", _now()
        self._emit("jobs", "job.started", {"job_id": job.id, "type": job.type})

        def progress(step: str, fraction: float) -> None:
            job.current_step, job.progress = step, round(float(fraction), 3)
            job.steps.append({"name": step, "at": _now(), "fraction": job.progress})
            self._emit("jobs", "job.progress", {"job_id": job.id, "step": step, "fraction": job.progress})

        try:
            job.result = runner(job, progress)
            job.status = "SUCCEEDED"
        except JobFailure as exc:
            job.status, job.error = "FAILED", str(exc)
        except Exception as exc:  # noqa: BLE001 - never leave a job RUNNING; internals stay in logs
            log.error("job failed", extra={"exc_type": type(exc).__name__}, exc_info=True)
            job.status, job.error = "FAILED", f"{type(exc).__name__}: job failed (see server logs with job id {job.id})"
        finally:
            job.finished_at = _now()
            self._emit("jobs", "job.finished", {"job_id": job.id, "status": job.status})

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
