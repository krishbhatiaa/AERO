"""Repository integration tests using asyncpg against a disposable test database.

    EWAI_TEST_DATABASE_URL=postgresql://postgres:pw@127.0.0.1:5432/ewai_test pytest backend/tests/test_repositories.py

The test DROPS and recreates the public schema of that database.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

asyncpg = pytest.importorskip(
    "asyncpg",
    reason="asyncpg not installed; repository integration tests need the asyncpg driver",
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("EWAI_TEST_DATABASE_URL", ""),
    reason="set EWAI_TEST_DATABASE_URL to a scratch test database",
)
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def event_loop():
    import asyncio

    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
async def pool():
    url = os.environ["EWAI_TEST_DATABASE_URL"]
    p = await asyncpg.create_pool(url, min_size=1, max_size=3)
    async with p.acquire() as conn:
        await conn.execute("DROP SCHEMA public CASCADE")
        await conn.execute("CREATE SCHEMA public")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS postgis")
        sql = (ROOT / "database/schema/001_init.sql").read_text()
        sql = sql.replace("CREATE EXTENSION IF NOT EXISTS postgis;", "")
        sql = sql.replace("BEGIN;", "").replace("COMMIT;", "")
        await conn.execute(sql)
    yield p
    await p.close()


@pytest.fixture
async def repos(pool):
    from app.repositories.postgres import (
        AlertRepository,
        AuditRepository,
        DatasetRepository,
        EventRepository,
        ForecastRepository,
        JobRepository,
        ModelRepository,
    )
    return {
        "events": EventRepository(pool),
        "forecasts": ForecastRepository(pool),
        "alerts": AlertRepository(pool),
        "datasets": DatasetRepository(pool),
        "jobs": JobRepository(pool),
        "models": ModelRepository(pool),
        "audit": AuditRepository(pool),
    }


def _event_data(event_id: str | None = None) -> dict:
    return {
        "id": event_id or str(uuid.uuid4()),
        "event_type": "EXTREME_RAINFALL",
        "status": "TRACKED_IN_FORECAST",
        "severity": "MODERATE",
        "data_kind": "SYNTHETIC_DEMO",
        "first_valid_time": "2025-06-01T00:00:00Z",
        "last_valid_time": "2025-06-01T12:00:00Z",
        "peak_intensity": 45.0,
        "peak_unit": "mm/6h",
        "peak_lead_hours": 18,
        "max_area_km2": 12000.0,
        "probability": 0.85,
        "confidence": "HIGH",
        "risk_score": 0.72,
        "provenance": {"source": "test"},
    }


def _alert_data(event_id: str) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "event_id": event_id,
        "event_type": "EXTREME_RAINFALL",
        "severity": "MODERATE",
        "forecast_window": "[2025-06-01T00:00:00Z,2025-06-01T12:00:00Z]",
        "probability": 0.85,
        "confidence": "HIGH",
        "uncertainty": {"radius_km": 50},
        "source": "test-engine",
        "model_version": "v0.1",
        "status": "ACTIVE",
        "data_kind": "SYNTHETIC_DEMO",
        "disclaimer": "test only",
    }


def _dataset_data(dataset_id: str | None = None) -> dict:
    return {
        "id": dataset_id or f"test-ds-{uuid.uuid4().hex[:8]}",
        "name": "Test Dataset",
        "data_kind": "SYNTHETIC_DEMO",
        "metadata": {"test": True},
    }


# --- EventRepository ---


@pytest.mark.anyio
async def test_event_crud(repos):
    repo = repos["events"]
    eid = str(uuid.uuid4())
    data = _event_data(eid)
    created_id = await repo.create(data)
    assert created_id == eid

    row = await repo.get(eid)
    assert row is not None
    assert row["event_type"] == "EXTREME_RAINFALL"
    assert row["severity"] == "MODERATE"

    updated = await repo.update(eid, {"severity": "SEVERE"})
    assert updated is True
    row2 = await repo.get(eid)
    assert row2["severity"] == "SEVERE"

    rows = await repo.list(limit=10)
    assert any(r["id"] == eid for r in rows)

    deleted = await repo.delete(eid)
    assert deleted is True
    assert await repo.get(eid) is None


@pytest.mark.anyio
async def test_event_list_pagination(repos):
    repo = repos["events"]
    ids = []
    for _ in range(5):
        eid = str(uuid.uuid4())
        await repo.create(_event_data(eid))
        ids.append(eid)
    page1 = await repo.list(limit=2, offset=0)
    page2 = await repo.list(limit=2, offset=2)
    assert len(page1) == 2
    assert len(page2) == 2
    assert set(r["id"] for r in page1) != set(r["id"] for r in page2)
    for eid in ids:
        await repo.delete(eid)


# --- ForecastRepository ---


@pytest.mark.anyio
async def test_forecast_crud(repos):
    repo = repos["forecasts"]
    fid = f"fcst-{uuid.uuid4().hex[:8]}"
    data = {
        "id": fid,
        "data_kind": "SYNTHETIC_DEMO",
        "initialization_time": "2025-06-01T00:00:00Z",
        "n_members": 3,
        "lead_hours": [6, 12, 18],
    }
    created_id = await repo.create(data)
    assert created_id == fid

    row = await repo.get(fid)
    assert row is not None
    assert row["n_members"] == 3

    updated = await repo.update(fid, {"n_members": 5})
    assert updated is True
    row2 = await repo.get(fid)
    assert row2["n_members"] == 5

    rows = await repo.list(limit=10)
    assert any(r["id"] == fid for r in rows)

    deleted = await repo.delete(fid)
    assert deleted is True


# --- AlertRepository ---


@pytest.mark.anyio
async def test_alert_crud(repos):
    events_repo = repos["events"]
    eid = str(uuid.uuid4())
    await events_repo.create(_event_data(eid))

    repo = repos["alerts"]
    aid = str(uuid.uuid4())
    data = _alert_data(eid)
    data["id"] = aid
    created_id = await repo.create(data)
    assert created_id == aid

    row = await repo.get(aid)
    assert row is not None
    assert row["event_id"] == eid

    updated = await repo.update(aid, {"status": "EXPIRED"})
    assert updated is True
    row2 = await repo.get(aid)
    assert row2["status"] == "EXPIRED"

    deleted = await repo.delete(aid)
    assert deleted is True
    await events_repo.delete(eid)


# --- DatasetRepository ---


@pytest.mark.anyio
async def test_dataset_crud(repos):
    repo = repos["datasets"]
    did = f"ds-{uuid.uuid4().hex[:8]}"
    data = _dataset_data(did)
    created_id = await repo.create(data)
    assert created_id == did

    row = await repo.get(did)
    assert row is not None
    assert row["name"] == "Test Dataset"

    updated = await repo.update(did, {"name": "Updated Dataset"})
    assert updated is True
    row2 = await repo.get(did)
    assert row2["name"] == "Updated Dataset"

    deleted = await repo.delete(did)
    assert deleted is True


# --- JobRepository ---


@pytest.mark.anyio
async def test_job_crud(repos):
    repo = repos["jobs"]
    jid = str(uuid.uuid4())
    data = {"id": jid, "status": "PENDING", "files": [{"name": "test.nc", "size": 1024}]}
    created_id = await repo.create(data)
    assert created_id == jid

    row = await repo.get(jid)
    assert row is not None
    assert row["status"] == "PENDING"

    updated = await repo.update(jid, {"status": "SUCCEEDED"})
    assert updated is True

    step_id = await repo.add_step(jid, "download", "SUCCEEDED")
    assert step_id > 0

    finding_id = await repo.add_finding(jid, "WARN", "MISSING_VAR", "tp not found", variable="tp")
    assert finding_id > 0

    deleted = await repo.delete(jid)
    assert deleted is True


# --- ModelRepository ---


@pytest.mark.anyio
async def test_model_crud(repos):
    repo = repos["models"]
    mid = await repo.create({"name": f"model-{uuid.uuid4().hex[:8]}", "kind": "tracker"})
    assert mid is not None

    row = await repo.get(mid)
    assert row is not None
    assert row["kind"] == "tracker"

    run_id = await repo.create_run({
        "model_id": int(mid),
        "version": "v1.0",
        "run_type": "training",
    })
    assert run_id is not None

    metric_id = await repo.add_metric(run_id, "rmse", 0.15, ci_low=0.12, ci_high=0.18)
    assert metric_id > 0

    deleted = await repo.delete(mid)
    assert deleted is True


# --- AuditRepository ---


@pytest.mark.anyio
async def test_audit_append_only(repos):
    repo = repos["audit"]
    aid = await repo.create({"actor": "test", "action": "login", "outcome": "ok"})
    assert aid is not None

    rows = await repo.list(limit=10)
    assert len(rows) >= 1

    with pytest.raises(NotImplementedError):
        await repo.update(aid, {"actor": "hacker"})
    with pytest.raises(NotImplementedError):
        await repo.delete(aid)


# --- Event insert/retrieve with geometry ---


@pytest.mark.anyio
async def test_event_with_geometry(repos, pool):
    repo = repos["events"]
    eid = str(uuid.uuid4())
    data = _event_data(eid)
    await repo.create(data)

    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE weather_events SET centroid = ST_SetSRID(ST_MakePoint(85.0, 20.0), 4326) WHERE id = $1",
            eid,
        )
        row = await conn.fetchrow("SELECT ST_X(centroid) as lon, ST_Y(centroid) as lat FROM weather_events WHERE id = $1", eid)
        assert row is not None
        assert abs(float(row["lon"]) - 85.0) < 0.001
        assert abs(float(row["lat"]) - 20.0) < 0.001

    await repo.delete(eid)


# --- Alert creation with regions ---


@pytest.mark.anyio
async def test_alert_with_regions(repos):
    events_repo = repos["events"]
    eid = str(uuid.uuid4())
    await events_repo.create(_event_data(eid))

    alert_repo = repos["alerts"]
    aid = str(uuid.uuid4())
    data = _alert_data(eid)
    data["id"] = aid
    data["regions"] = [
        {"region_id": "test-region", "polygon_kind": "RISK", "intersect_area_km2": 500.0, "fraction_of_region": 0.3},
    ]
    await alert_repo.create(data)

    row = await alert_repo.get(aid)
    assert row is not None

    await alert_repo.delete(aid)
    await events_repo.delete(eid)
