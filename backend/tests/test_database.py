"""PostGIS integration tests. Skipped unless EWAI_TEST_DATABASE_URL points at a SCRATCH database whose name contains 'test'.

    EWAI_TEST_DATABASE_URL=postgresql://postgres:pw@127.0.0.1:5432/ewai_test pytest backend/tests/test_database.py

The test DROPS and recreates the public schema of that database.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")
URL = os.environ.get("EWAI_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not URL or "test" not in URL.rsplit("/", 1)[-1], reason="set EWAI_TEST_DATABASE_URL to a scratch *test* database")
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def conn():
    with psycopg.connect(URL, autocommit=True) as c:
        c.execute("DROP SCHEMA public CASCADE")
        c.execute("CREATE SCHEMA public")
        c.execute("CREATE EXTENSION IF NOT EXISTS postgis")
        c.execute((ROOT / "database/schema/001_init.sql").read_text().replace("CREATE EXTENSION IF NOT EXISTS postgis;", ""))
        yield c


def test_schema_has_all_spec_tables_and_gist_indexes(conn):
    tables = {r[0] for r in conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'")}
    spec = {"weather_events", "event_tracks", "forecast_runs", "forecast_members", "weather_variables", "anomaly_regions", "downscaled_products",
            "model_runs", "model_metrics", "alerts", "geographic_regions", "data_sources", "data_ingestion_jobs", "users", "audit_logs"}
    assert spec <= tables
    gist = {r[0] for r in conn.execute("SELECT indexname FROM pg_indexes WHERE schemaname='public' AND indexdef ILIKE '%USING gist%'")}
    assert {"gist_events_footprint", "gist_georegions_geom", "gist_impact_geom", "gist_alerts_window"} <= gist


def test_audit_log_is_append_only(conn):
    conn.execute("INSERT INTO audit_logs (actor, action, outcome) VALUES ('t', 'a', 'ok')")
    for sql in ("UPDATE audit_logs SET actor='x'", "DELETE FROM audit_logs", "TRUNCATE audit_logs"):
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            conn.execute(sql)
    assert conn.execute("SELECT count(*) FROM audit_logs").fetchone()[0] == 1


def test_constraints_reject_bad_rows(conn):
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("INSERT INTO weather_events (id,event_type,status,severity,data_kind,first_valid_time,last_valid_time,provenance) "
                     "VALUES (gen_random_uuid(),'OTHER','x','LOW','SYNTHETIC_DEMO','2000-01-02','2000-01-01','{}')")
    with pytest.raises(psycopg.errors.InvalidTextRepresentation):
        conn.execute("INSERT INTO geographic_regions (id,level,name,geom,boundary_source) VALUES ('x','PLANET','n',ST_GeomFromText('MULTIPOLYGON(((0 0,1 0,1 1,0 0)))',4326),'s')")


def test_seed_script_cross_checks_postgis_against_shapely():
    r = subprocess.run([sys.executable, str(ROOT / "scripts/seed_db.py"), "--database-url", URL], capture_output=True, text=True, timeout=180, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "cross-check: PASS" in r.stdout and "Odisha" in r.stdout
