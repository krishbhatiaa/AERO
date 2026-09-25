from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from app.core.config import Settings
from app.core.security import hash_api_key
from app.main import create_app
from fastapi.testclient import TestClient

from ml.pipeline.demo import DemoResult, run_demo_pipeline


@pytest.fixture(scope="session")
def pipeline_result() -> DemoResult:
    return run_demo_pipeline()


def make_settings(tmp: Path, **overrides) -> Settings:  # noqa: ANN003
    base = dict(env="test", data_path=str(tmp / "data"), audit_log_path=str(tmp / "audit.log"), cors_origins="http://localhost:5173",
                rate_limit_per_minute=10_000, redis_url="", database_url="")
    base.update(overrides)
    return Settings(_env_file=None, **base)


@pytest.fixture()
def client(tmp_path: Path, pipeline_result: DemoResult) -> Iterator[TestClient]:
    app = create_app(make_settings(tmp_path), preloaded=pipeline_result)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def secured(tmp_path: Path, pipeline_result: DemoResult) -> Iterator[TestClient]:
    keys = ",".join(f"{n}:{r}:{hash_api_key(k)}" for n, r, k in (("vera", "viewer", "viewer-key"), ("ana", "analyst", "analyst-key")))
    app = create_app(make_settings(tmp_path, auth_mode="api_key", api_keys=keys), preloaded=pipeline_result)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def event_id(client: TestClient) -> str:
    return client.get("/api/v1/events").json()["data"][0]["id"]


def wait_for_job(client: TestClient, job_id: str, timeout: float = 90.0, headers: dict | None = None) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        job = client.get(f"/api/v1/jobs/{job_id}", headers=headers or {}).json()["data"]
        if job["status"] in ("SUCCEEDED", "FAILED"):
            return job
        time.sleep(0.25)
    raise AssertionError("job did not finish in time")


Waiter = Callable[..., dict]
