"""Seed PostgreSQL/PostGIS with the products of the SYNTHETIC demo pipeline and cross-check PostGIS against shapely.

Usage:
    psql "$DATABASE_URL" -f database/schema/001_init.sql          # once
    python scripts/seed_db.py --database-url "$DATABASE_URL"

Everything inserted is labelled SYNTHETIC_DEMO. The script is idempotent (it truncates the seeded tables first,
never audit_logs). It finishes by running the reference PostGIS intersection query and comparing the result with
the in-process implementation used by the API; a mismatch is a non-zero exit.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import psycopg
import shapely
import yaml
from shapely.geometry import MultiPolygon, Polygon

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

from app.services import alerts as alert_service  # noqa: E402
from app.services import datasets as dataset_service  # noqa: E402
from app.services import events as ev  # noqa: E402
from app.services import registry  # noqa: E402

from data_pipeline.adapters.registry import all_descriptors  # noqa: E402
from ml.core.config import config_dir  # noqa: E402
from ml.pipeline.demo import DemoResult, run_demo_pipeline, valid_time  # noqa: E402


def multi(geom: shapely.geometry.base.BaseGeometry) -> str:
    g = MultiPolygon([geom]) if isinstance(geom, Polygon) else geom
    return g.wkt


def seed(conn: psycopg.Connection, result: DemoResult) -> tuple[str, int]:
    track = result.primary
    summary = ev.event_summary(result, track)
    alert = alert_service.build_alert(result, track)
    eid, sc = summary["id"], result.scenario
    pid = result.provenance.dataset_id
    with conn.transaction(), conn.cursor() as cur:
        cur.execute("TRUNCATE weather_events, forecast_runs, datasets, geographic_regions, data_sources, weather_variables, "
                    "models, model_runs, alerts CASCADE")
        # --- reference data
        for name, spec in yaml.safe_load((config_dir() / "variables.yaml").read_text())["variables"].items():
            lo, hi = spec["valid_range"]
            cur.execute("INSERT INTO weather_variables VALUES (%s,%s,%s,%s,%s)", (name, spec["long_name"], spec["units"], lo, hi))
        src_ids: dict[str, int] = {}
        for d in all_descriptors():
            cur.execute("INSERT INTO data_sources (name,data_kind,access_status,nominal_resolution_deg,description) VALUES (%s,%s,%s,%s,%s) RETURNING id",
                        (d.name, d.data_kind.value, d.status.value, d.nominal_resolution_deg, d.message))
            src_ids[d.name] = cur.fetchone()[0]
        regions = json.loads((ROOT / "sample_data/boundaries/india_states_domain.geojson").read_text())["features"]
        for i, f in enumerate(regions):
            cur.execute("INSERT INTO geographic_regions VALUES (%s,'STATE',%s,%s,ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326)),%s,%s)",
                        (f"state:{f['properties'].get('code') or i}", f["properties"].get("code"), f["properties"]["name"],
                         json.dumps(f["geometry"]), "Natural Earth 1:10m admin-1 (public domain; NOT an official boundary set)", "5.x-clipped"))
        # --- datasets and forecast run
        for d in dataset_service.demo_datasets(result):
            g = d["geographic_extent"]
            cur.execute("INSERT INTO datasets (id,source_id,name,data_kind,grid,geographic_extent,temporal_start,temporal_end,metadata) "
                        "VALUES (%s,%s,%s,%s,%s,ST_MakeEnvelope(%s,%s,%s,%s,4326),%s,%s,%s)",
                        (d["id"], src_ids["SYNTHETIC"], d["name"], d["data_kind"], json.dumps(d["grid"]), g["west"], g["south"], g["east"], g["north"],
                         d["temporal_extent"]["start"], d["temporal_extent"]["end"], json.dumps({"variables": d["variables"]})))
        cur.execute("INSERT INTO forecast_runs (id,dataset_id,source_id,data_kind,initialization_time,n_members,lead_hours) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (pid, f"{pid}:forecast", src_ids["SYNTHETIC"], "SYNTHETIC_DEMO", sc.config.init_time, result.member_positions.shape[0] + 1, result.lead_hours))
        for m in range(result.member_positions.shape[0] + 1):
            cur.execute("INSERT INTO forecast_members (forecast_run_id, member) VALUES (%s,%s)", (pid, m))
        # --- registry
        model_ids: dict[str, int] = {}
        for m in registry.list_models(result):
            cur.execute("INSERT INTO models (name,kind) VALUES (%s,%s) RETURNING id", (m["name"], m["kind"]))
            model_ids[m["name"]] = cur.fetchone()[0]
            cur.execute("INSERT INTO model_runs (model_id,version,run_type,status,architecture,parameters,config_hash,seed,device) "
                        "VALUES (%s,%s,'evaluation','baseline',%s,0,%s,%s,'cpu') RETURNING id",
                        (model_ids[m["name"]], m["version"], m["architecture"], result.config_digest, sc.config.seed))
            run_id = cur.fetchone()[0]
            for k, v in (m["metrics"] or {}).items():
                cur.execute("INSERT INTO model_metrics (model_run_id,name,value,split,n) VALUES (%s,%s,%s,'synthetic',%s)", (run_id, k, float(v), len(result.lead_hours)))
        # --- event, tracks, geometries
        footprint = shapely.union_all([p.region.footprint for p in track.observed_points])
        peak = ev.peak_point(track)
        cur.execute("INSERT INTO weather_events (id,event_type,status,severity,data_kind,first_valid_time,last_valid_time,peak_intensity,peak_unit,"
                    "peak_lead_hours,max_area_km2,probability,confidence,risk_score,footprint,centroid,forecast_run_id,dataset_id,provenance) "
                    "VALUES (%s,'EXTREME_RAINFALL',%s,%s,'SYNTHETIC_DEMO',%s,%s,%s,'mm/6h',%s,%s,%s,%s,%s,ST_GeomFromText(%s,4326),"
                    "ST_SetSRID(ST_MakePoint(%s,%s),4326),%s,%s,%s)",
                    (eid, summary["status"], summary["severity"], summary["first_valid_time"], summary["last_valid_time"],
                     summary["peak_intensity"]["value"], summary["peak_lead_hours"], summary["max_area_km2"], summary["probability"],
                     summary["confidence"], summary["risk_score"], multi(footprint), peak.lon, peak.lat, pid, f"{pid}:forecast", json.dumps(summary["provenance"])))
        for p in track.observed_points:
            cur.execute("INSERT INTO event_tracks (event_id,member,valid_time,lead_hours,centroid,footprint,area_km2,intensity,speed_kmh,bearing_deg,"
                        "uncertainty_radius_km,track_source,observed) VALUES (%s,0,%s,%s,ST_SetSRID(ST_MakePoint(%s,%s),4326),ST_GeomFromText(%s,4326),"
                        "%s,%s,%s,%s,%s,'BASELINE_KALMAN',true)",
                        (eid, valid_time(result, int(p.time_h)), int(p.time_h), p.lon, p.lat, multi(p.region.footprint), p.area_km2, p.max_intensity,
                         p.speed_kmh, p.bearing_deg % 360.0, p.uncertainty_radius_km))
        for k in range(result.member_positions.shape[0]):
            for i, h in enumerate(result.lead_hours):
                lat, lon = result.member_positions[k, i]
                if lat == lat:
                    cur.execute("INSERT INTO event_tracks (event_id,member,valid_time,lead_hours,centroid,track_source) VALUES (%s,%s,%s,%s,ST_SetSRID(ST_MakePoint(%s,%s),4326),'ENSEMBLE_MEMBER')",
                                (eid, k + 1, valid_time(result, h), h, float(lon), float(lat)))
        for e in result.extrapolation:
            cur.execute("INSERT INTO event_tracks (event_id,member,valid_time,lead_hours,centroid,uncertainty_radius_km,track_source,observed) VALUES (%s,0,%s,%s,ST_SetSRID(ST_MakePoint(%s,%s),4326),%s,'EXTRAPOLATION',false)",
                        (eid, valid_time(result, int(e["time_h"])), int(e["time_h"]), e["lon"], e["lat"], e["uncertainty_radius_km"]))
        for lead, imp in result.impact.items():
            for kind, geom in imp["geometries"].items():
                cur.execute("INSERT INTO impact_geometries (event_id,kind,valid_time,geom,params) VALUES (%s,%s,%s,ST_GeomFromText(%s,4326),%s)",
                            (eid, kind.upper(), valid_time(result, lead), multi(geom), json.dumps({"lead_hours": lead, "uncertainty_radius_km": imp["uncertainty_radius_km"]})))
        # --- alert
        w = alert["forecast_window"]
        cur.execute("INSERT INTO alerts (id,event_id,event_type,severity,forecast_window,probability,confidence,uncertainty,source,model_version,status,data_kind,risk_polygon,disclaimer) "
                    "VALUES (%s,%s,'EXTREME_RAINFALL',%s,tstzrange(%s,%s,'[]'),%s,%s,%s,%s,%s,%s,'SYNTHETIC_DEMO',ST_GeomFromText(%s,4326),%s)",
                    (alert["id"], eid, alert["severity"], w["start"], w["end"], alert["probability"], alert["confidence"], json.dumps(alert["uncertainty"]),
                     alert["source"], alert["model_version"], alert["status"], multi(shapely.geometry.shape(alert["geometry"]["risk_polygon"])), alert["disclaimer"]))
    return eid, int(peak.time_h)


REFERENCE_QUERY = """
SELECT r.name,
       ST_Area(ST_Intersection(r.geom, g.geom)::geography) / 1e6 AS intersect_area_km2
FROM   geographic_regions r
JOIN   impact_geometries g ON g.event_id = %s AND g.kind = 'RISK' AND g.valid_time = %s
WHERE  ST_Intersects(r.geom, g.geom)
ORDER  BY intersect_area_km2 DESC
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--database-url", required=True)
    args = ap.parse_args()
    result = run_demo_pipeline()
    with psycopg.connect(args.database_url) as conn:
        eid, peak_lead = seed(conn, result)
        rows = conn.execute(REFERENCE_QUERY, (eid, valid_time(result, peak_lead))).fetchall()
        counts = {}
        for table in ("weather_events", "event_tracks", "impact_geometries", "geographic_regions", "alerts", "model_metrics"):  # constant names
            counts[table] = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]  # noqa: S608
    print("seeded:", counts)
    pg = {name: area for name, area in rows}
    py = {r["name"]: r["intersect_area_km2"] for r in result.impact[peak_lead]["regions_risk"]}
    print("PostGIS intersection (km2):", {k: round(v) for k, v in pg.items()})
    print("shapely intersection (km2):", {k: round(v) for k, v in py.items()})
    ok = set(pg) == set(py) and all(abs(pg[k] - py[k]) / max(py[k], 1.0) < 0.02 for k in py if py[k] > 100)
    print("cross-check:", "PASS (areas agree within 2 %; both are ellipsoidal areas)" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
