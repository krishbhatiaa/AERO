import base64
import json

import numpy as np
import pytest
from app.core.audit import AuditLogger
from app.core.cache import MemoryCache, RedisCache, create_cache
from app.core.config import Settings
from app.core.security import RateLimiter, hash_api_key, parse_api_keys
from tests.conftest import make_settings

API = "/api/v1"


def test_route_table_is_complete(client):
    schema = client.get(f"{API}/openapi.json").json()["paths"]
    expected = {"/health", "/live", "/ready", "/capabilities", "/events", "/events/{event_id}", "/events/{event_id}/trajectory",
                "/events/{event_id}/impact", "/events/{event_id}/uncertainty", "/events/{event_id}/explain", "/events/{event_id}/downscaled",
                "/forecasts", "/forecasts/{run_id}", "/fields", "/alerts", "/alerts/{alert_id}", "/alerts/{alert_id}/geojson",
                "/predictions", "/jobs", "/jobs/{job_id}", "/datasets", "/datasets/{dataset_id}", "/data-sources", "/models", "/model-runs",
                "/evaluation/downscaling", "/evaluation/tracking"}
    assert expected <= {p.removeprefix(API) for p in schema}, expected - {p.removeprefix(API) for p in schema}


def test_health_live_ready_and_capabilities(client):
    assert client.get(f"{API}/live").json() == {"status": "alive"}
    h = client.get(f"{API}/health").json()["data"]
    assert h["status"] == "ok" and h["mode"]["data_kind_in_use"] == "SYNTHETIC_DEMO" and h["mode"]["demo_mode"] is True
    r = client.get(f"{API}/ready")
    assert r.status_code == 200
    deps = r.json()["data"]["dependencies"]
    assert deps["storage"]["status"] == "ok" and deps["database"]["status"] == "not_configured" and deps["products"]["status"] == "ok"
    assert deps["ml_device"]["resolved"] in ("cpu", "cuda")
    cap = client.get(f"{API}/capabilities").json()["data"]
    statuses = {c["status"] for c in cap["capabilities"]}
    assert statuses <= {"IMPLEMENTED", "PARTIALLY_IMPLEMENTED", "REQUIRES_REAL_DATA", "REQUIRES_GPU_TRAINING", "RESEARCH_EXTENSION"}
    ids = {c["id"]: c["status"] for c in cap["capabilities"]}
    assert ids["diffusion"] == "REQUIRES_GPU_TRAINING" and ids["restricted_sources"] == "REQUIRES_REAL_DATA" and ids["globe3d"] == "RESEARCH_EXTENSION"
    assert sum(cap["counts"].values()) == len(cap["capabilities"])


def test_ready_reports_unreachable_dependencies_without_leaking_urls(tmp_path, pipeline_result):
    from app.main import create_app
    from fastapi.testclient import TestClient

    s = make_settings(tmp_path, redis_url="redis://user:secretpw@127.0.0.1:1/0", database_url="postgresql://u:pw@127.0.0.1:1/db")
    with TestClient(create_app(s, preloaded=pipeline_result)) as c:
        r = c.get(f"{API}/ready")
        assert r.status_code == 503 and r.headers["content-type"].startswith("application/problem+json")
        assert "secretpw" not in r.text and "pw@" not in r.text
        rep = r.json()["report"]["dependencies"]
        assert rep["redis"]["status"] == "down" and rep["database"]["status"] == "down"
        assert c.get(f"{API}/live").status_code == 200
        assert c.app.state.cache.name == "memory"  # graceful Redis fallback


def test_request_id_and_security_headers(client):
    r = client.get(f"{API}/health", headers={"X-Request-ID": "abc-123"})
    assert r.headers["x-request-id"] == "abc-123" and r.json()["meta"]["request_id"] == "abc-123"
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"] and r.headers["cache-control"] == "no-store"
    bad = client.get(f"{API}/health", headers={"X-Request-ID": "x" * 200})
    assert len(bad.headers["x-request-id"]) == 32
    inj = client.get(f"{API}/health", headers={"X-Request-ID": "a b\tc"})
    assert " " not in inj.headers["x-request-id"]


def test_errors_are_problem_json_without_internals(client):
    r = client.get(f"{API}/events/does-not-exist")
    assert r.status_code == 404 and r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["code"] == "EVENT_NOT_FOUND" and body["request_id"] == r.headers["x-request-id"] and "Traceback" not in r.text
    v = client.get(f"{API}/events", params={"page": 0, "page_size": 999})
    assert v.status_code == 422 and v.json()["code"] == "VALIDATION_ERROR" and len(v.json()["errors"]) == 2
    assert client.get(f"{API}/nope").json()["code"] == "HTTP_404"
    assert client.post(f"{API}/health").status_code == 405


def test_cors_is_restricted_to_configured_origins(client):
    ok = client.get(f"{API}/health", headers={"Origin": "http://localhost:5173"})
    assert ok.headers["access-control-allow-origin"] == "http://localhost:5173"
    evil = client.get(f"{API}/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in evil.headers
    with pytest.raises(ValueError):
        _ = Settings(_env_file=None, cors_origins="*").cors_origin_list


def test_events_listing_filters_sorting_pagination(client):
    r = client.get(f"{API}/events")
    body = r.json()
    assert r.status_code == 200 and body["meta"]["total"] == 1 and body["meta"]["page"] == 1
    e = body["data"][0]
    assert e["data_kind"] == "SYNTHETIC_DEMO" and e["severity_is_official"] is False and e["event_type"] == "EXTREME_RAINFALL"
    assert e["first_valid_time"].endswith("Z") and e["provenance"]["timezone"] == "UTC" and e["provenance"]["checkpoint_sha256"] is None
    assert e["attributes"]["cyclone_like_signature"] is True and "SYNTHETIC" in e["disclaimer"]
    assert client.get(f"{API}/events", params={"severity": e["severity"]}).json()["meta"]["total"] == 1
    other = "LOW" if e["severity"] != "LOW" else "SEVERE"
    assert client.get(f"{API}/events", params={"severity": other}).json()["meta"]["total"] == 0
    assert client.get(f"{API}/events", params={"severity": "BOGUS"}).status_code == 422
    assert client.get(f"{API}/events", params={"event_type": "heatwave"}).json()["meta"]["total"] == 0
    assert client.get(f"{API}/events", params={"data_kind": "OBSERVED"}).json()["meta"]["total"] == 0
    inside = "80,12,92,24"
    assert client.get(f"{API}/events", params={"bbox": inside}).json()["meta"]["total"] == 1
    assert client.get(f"{API}/events", params={"bbox": "0,0,10,10"}).json()["meta"]["total"] == 0
    assert client.get(f"{API}/events", params={"bbox": "10,10,0,0"}).status_code == 422
    assert client.get(f"{API}/events", params={"bbox": "a,b,c,d"}).status_code == 422
    assert client.get(f"{API}/events", params={"sort": "-peak_intensity,first_valid_time"}).status_code == 200
    assert client.get(f"{API}/events", params={"sort": "password"}).status_code == 422
    assert client.get(f"{API}/events", params={"to": "1999-01-01T00:00:00Z"}).json()["meta"]["total"] == 0
    assert client.get(f"{API}/events", params={"from": "1999-01-01T00:00:00Z"}).json()["meta"]["total"] == 1
    assert client.get(f"{API}/events", params={"page": 2}).json()["data"] == []
    assert client.get(f"{API}/events/{e['id']}").json()["data"]["id"] == e["id"]


def test_trajectory_geojson_contract(client, event_id):
    d = client.get(f"{API}/events/{event_id}/trajectory").json()["data"]
    assert d["type"] == "FeatureCollection" and d["meta"]["timezone"] == "UTC" and d["meta"]["data_kind"] == "SYNTHETIC_DEMO"
    kinds = {f["properties"]["kind"] for f in d["features"]}
    assert {"tracked", "extrapolation", "tracked_point", "extrapolated_point", "uncertainty_envelope", "ensemble_members"} <= kinds
    pts = [f for f in d["features"] if f["properties"]["kind"] == "tracked_point"]
    assert [p["properties"]["lead_hours"] for p in pts] == list(range(0, 49, 6))
    assert all(-180 <= p["geometry"]["coordinates"][0] <= 180 and -90 <= p["geometry"]["coordinates"][1] <= 90 for p in pts)
    assert pts[-1]["geometry"]["coordinates"][1] > pts[0]["geometry"]["coordinates"][1]
    ex = [f for f in d["features"] if f["properties"]["kind"] == "extrapolated_point"]
    assert all(f["properties"]["data_kind"] == "MODEL_PREDICTION" for f in ex)
    env = next(f for f in d["features"] if f["properties"]["kind"] == "uncertainty_envelope")
    assert env["geometry"]["type"] in ("Polygon", "MultiPolygon") and "Not an NHC cone" in env["properties"]["label"]


def test_impact_uncertainty_explain_and_downscaled(client, event_id):
    imp = client.get(f"{API}/events/{event_id}/impact").json()["data"]
    kinds = {f["properties"]["kind"]: f["properties"]["area_km2"] for f in imp["features"]}
    assert kinds["impact"] < kinds["risk"] < kinds["uncertainty"]
    assert imp["risk"]["is_official_warning_category"] is False and any(r["name"] == "Odisha" for r in imp["regions"]["risk"])
    assert client.get(f"{API}/events/{event_id}/impact", params={"lead_hours": 7}).status_code == 422
    assert client.get(f"{API}/events/{event_id}/impact", params={"lead_hours": 24}).status_code == 200
    u = client.get(f"{API}/events/{event_id}/uncertainty").json()["data"]
    assert u["n_members"] == 11 and len(u["steps"]) == 9 and any("diffusion" in n for n in u["notes"])
    assert all(s["confidence"] in ("HIGH", "MEDIUM", "LOW") for s in u["steps"])
    x = client.get(f"{API}/events/{event_id}/explain").json()["data"]
    assert len(x["factors"]) == 9 and any("do not establish physical causes" in n for n in x["notes"])
    d = client.get(f"{API}/events/{event_id}/downscaled").json()["data"]
    assert d["learned_model_available"] is False and "BASELINE" in d["notice"] and len(d["methods"]) == 4


def test_fields_are_decodable_labelled_and_cached(client):
    def get(**p):
        return client.get(f"{API}/fields", params=p)

    r = get(product="forecast", variable="tp", lead_hours=36)
    d = r.json()["data"]
    arr = np.frombuffer(base64.b64decode(d["values_b64"]), dtype="<f4").reshape(d["shape"])
    assert d["shape"] == [120, 120] and d["data_kind"] == "SYNTHETIC_DEMO" and "SYNTHETIC" in d["label"] and d["row_order"] == "south_to_north"
    assert float(arr.max()) == pytest.approx(d["max"]) and arr.min() >= 0 and d["bounds"][0] < d["bounds"][2]
    fine = get(product="downscaled", variable="tp", lead_hours=36, method="bicubic_conservative").json()["data"]
    assert fine["shape"] == [240, 240] and "BASELINE" in fine["label"] and fine["resolution_km"]["north_south"] < d["resolution_km"]["north_south"]
    msl = get(product="forecast", variable="msl", lead_hours=36).json()["data"]
    assert 940 < msl["min"] < 1010 and msl["units"] == "hPa"
    assert get(product="anomaly", variable="anomaly", lead_hours=36).json()["data"]["max"] <= 1.0
    assert get(product="truth", variable="tp", lead_hours=0).json()["data"]["shape"] == [240, 240]
    assert get(product="forecast", variable="tp", lead_hours=7).status_code == 422
    assert get(product="bogus").status_code == 422 and get(product="downscaled", variable="msl").status_code == 422
    assert get(product="downscaled", variable="tp", method="magic").status_code == 422
    assert get(product="forecast", variable="tp", lead_hours=36).json()["data"]["values_b64"] == d["values_b64"]
    fr = client.get(f"{API}/forecasts").json()["data"][0]
    assert fr["source"] == "SYNTHETIC" and fr["n_members"] == 11 and fr["lead_hours"][-1] == 48
    assert client.get(f"{API}/forecasts/{fr['id']}").status_code == 200 and client.get(f"{API}/forecasts/x").status_code == 404


def test_alerts_are_labelled_unofficial_and_exportable(client, event_id):
    a = client.get(f"{API}/alerts").json()["data"][0]
    assert a["event_id"] == event_id and a["severity_is_official"] is False and a["data_kind"] == "SYNTHETIC_DEMO"
    for k in ("event_type", "severity", "location", "affected_area", "forecast_window", "probability", "confidence", "uncertainty", "source", "model_version", "created_at"):
        assert k in a
    assert a["forecast_window"]["timezone"] == "UTC" and "Not an official warning" in a["risk"]["disclaimer"] and "Odisha" in a["location"]["regions"]
    assert "Verify" in a["verification"] and "emergency" not in json.dumps(a).lower()
    assert client.get(f"{API}/alerts", params={"severity": "BOGUS"}).status_code == 422
    assert client.get(f"{API}/alerts", params={"event_id": "zzz"}).json()["meta"]["total"] == 0
    g = client.get(f"{API}/alerts/{a['id']}/geojson")
    assert g.headers["content-type"].startswith("application/geo+json") and "attachment" in g.headers["content-disposition"]
    assert len(g.json()["features"]) == 3 and client.get(f"{API}/alerts/nope").status_code == 404


def test_datasets_sources_models_and_evaluation(client):
    ds = client.get(f"{API}/datasets").json()["data"]
    assert {d["id"].split(":")[1] for d in ds} == {"forecast", "truth", "climate"} and all(d["data_kind"] == "SYNTHETIC_DEMO" for d in ds)
    assert client.get(f"{API}/datasets/{ds[0]['id']}").status_code == 200 and client.get(f"{API}/datasets/zzz").status_code == 404
    src = client.get(f"{API}/data-sources").json()["data"]
    st = {s["name"]: s["status"] for s in src["sources"]}
    assert st["NEPS-G"] == "NOT_CONFIGURED" and st["SYNTHETIC"] == "AVAILABLE"
    assert src["target_source_resolution"]["substituted"] is True and "SYNTHETIC" in src["target_source_resolution"]["message"]
    models = client.get(f"{API}/models").json()["data"]
    assert models and all(m["learned"] is False and m["checkpoint"] is None and m["parameters"] == 0 for m in models)
    assert any(m["status"] == "BASELINE_DEFAULT" and m["name"] == "downscale-bicubic_conservative" for m in models)
    runs = client.get(f"{API}/model-runs").json()["data"]
    assert {r["type"] for r in runs} == {"evaluation"} and all(r["data_kind"] == "SYNTHETIC_DEMO" for r in runs)
    ev = client.get(f"{API}/evaluation/downscaling").json()["data"]
    assert ev["learned_models_evaluated"] == [] and "not real-world skill" in ev["caveat"] and len(ev["methods"]) == 4
    m = ev["methods"][0]["metrics"]
    assert {"rmse", "peak_error", "p95_error", "p99_error", "extreme_recall", "extreme_precision", "psd_ratio_band"} <= set(m)
    tr = client.get(f"{API}/evaluation/tracking").json()["data"]
    assert tr["hindcast"]["kalman_km"]["1"] < tr["hindcast"]["persistence_km"]["1"] and "mechanics" in tr["caveat"]


def test_prediction_job_lifecycle_and_validation(client):
    from tests.conftest import wait_for_job

    bad = client.post(f"{API}/predictions", json={"scenario_seed": -1, "n_members": 1})
    assert bad.status_code == 422 and len(bad.json()["errors"]) == 2
    r = client.post(f"{API}/predictions", json={"scenario_seed": 11, "n_members": 4})
    assert r.status_code == 202 and r.headers["location"].endswith(r.json()["data"]["id"])
    job = wait_for_job(client, r.json()["data"]["id"])
    assert job["status"] == "SUCCEEDED" and job["progress"] == 1.0 and job["steps"][-1]["name"] == "done"
    assert job["request_id"] == r.headers["x-request-id"] and job["result"]["data_kind"] == "SYNTHETIC_DEMO"
    new_id = client.get(f"{API}/events").json()["data"][0]["id"]
    assert new_id in job["result"]["event_ids"]
    assert client.get(f"{API}/forecasts").json()["data"][0]["n_members"] == 5
    assert client.get(f"{API}/jobs/nope").status_code == 404
    assert any(j["id"] == job["id"] for j in client.get(f"{API}/jobs").json()["data"])


def test_ingest_job_and_dataset_listing(client):
    from tests.conftest import wait_for_job

    assert client.post(f"{API}/jobs", json={"type": "ingest", "params": {"source": "synthetic", "dataset_id": "../etc"}}).status_code == 422
    assert client.post(f"{API}/jobs", json={"type": "ingest", "params": {"source": "wget"}}).status_code == 422
    assert client.post(f"{API}/jobs", json={"type": "bogus"}).status_code == 422
    r = client.post(f"{API}/jobs", json={"type": "ingest", "params": {"source": "synthetic", "dataset_id": "syn-ingest-1"}})
    job = wait_for_job(client, r.json()["data"]["id"])
    assert job["status"] == "SUCCEEDED" and job["result"]["validation_ok"] is True
    ids = [d["id"] for d in client.get(f"{API}/datasets").json()["data"]]
    assert "syn-ingest-1" in ids
    fail = client.post(f"{API}/jobs", json={"type": "ingest", "params": {"source": "neps", "dataset_id": "neps-x"}})
    failed = wait_for_job(client, fail.json()["data"]["id"])
    assert failed["status"] == "FAILED" and "variable mapping is empty" in failed["error"] and "Traceback" not in json.dumps(failed)
    assert str(client.app.state.settings.data_path) not in json.dumps(failed)


def test_body_size_limit(tmp_path, pipeline_result):
    from app.main import create_app
    from fastapi.testclient import TestClient

    s = make_settings(tmp_path, max_body_bytes=2048)
    with TestClient(create_app(s, preloaded=pipeline_result)) as c:
        r = c.post(f"{API}/predictions", content=b"x" * 5000, headers={"Content-Type": "application/json"})
        assert r.status_code == 413 and r.json()["code"] == "BODY_TOO_LARGE"
        ok = c.post(f"{API}/predictions", json={"scenario_seed": 3, "n_members": 2})
        assert ok.status_code == 202


def test_authentication_authorisation_and_audit(secured, tmp_path):
    assert secured.get(f"{API}/health").status_code == 200 and secured.get(f"{API}/live").status_code == 200
    r = secured.get(f"{API}/events")
    assert r.status_code == 401 and r.headers["www-authenticate"] == "ApiKey"
    assert secured.get(f"{API}/events", headers={"X-API-Key": "wrong"}).status_code == 401
    v = {"X-API-Key": "viewer-key"}
    assert secured.get(f"{API}/events", headers=v).status_code == 200
    forbidden = secured.post(f"{API}/predictions", json={}, headers=v)
    assert forbidden.status_code == 403 and forbidden.json()["code"] == "FORBIDDEN"
    ok = secured.post(f"{API}/predictions", json={"scenario_seed": 5, "n_members": 2}, headers={"X-API-Key": "analyst-key"})
    assert ok.status_code == 202
    log = AuditLogger(secured.app.state.settings.audit_log_path).read()
    actions = [(e["action"], e["outcome"]) for e in log]
    assert ("auth.failed", "denied") in actions and ("authz.denied", "denied") in actions and ("job.created", "ok") in actions
    assert "analyst-key" not in json.dumps(log) and "viewer-key" not in json.dumps(log)
    assert next(e for e in log if e["action"] == "job.created")["actor"] == "ana"


def test_rate_limiting(tmp_path, pipeline_result):
    from app.main import create_app
    from fastapi.testclient import TestClient

    with TestClient(create_app(make_settings(tmp_path, rate_limit_per_minute=3), preloaded=pipeline_result)) as c:
        codes = [c.get(f"{API}/events").status_code for _ in range(5)]
        assert codes[:3] == [200, 200, 200] and codes[3:] == [429, 429]
        r = c.get(f"{API}/events")
        assert r.json()["code"] == "RATE_LIMITED" and int(r.headers["retry-after"]) >= 1 and r.headers["x-content-type-options"] == "nosniff"
        assert c.get(f"{API}/live").status_code == 200  # probes are exempt


def test_rate_limiter_window_and_key_parsing():
    rl = RateLimiter(2, window_s=10.0)
    assert rl.check("a", 0.0)[0] and rl.check("a", 1.0)[0]
    ok, retry = rl.check("a", 2.0)
    assert not ok and 1 <= retry <= 10 and rl.check("b", 2.0)[0] and rl.check("a", 11.5)[0]
    assert parse_api_keys("") == {}
    for bad in ("nocolons", "a:root:" + "0" * 64, "a:viewer:short"):
        with pytest.raises(ValueError):
            parse_api_keys(bad)
    assert hash_api_key("k") == hash_api_key("k") and len(hash_api_key("k")) == 64


def test_websocket_hello_and_job_events(client):
    from tests.conftest import wait_for_job

    with client.websocket_connect(f"{API}/ws?channels=jobs") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello" and hello["payload"]["channels"] == ["jobs"] and hello["ts_utc"].endswith("Z")
        r = client.post(f"{API}/predictions", json={"scenario_seed": 21, "n_members": 2})
        seen = set()
        while "job.finished" not in seen:
            m = ws.receive_json()
            seen.add(m["type"])
            assert m["payload"]["channel"] == "jobs" and m["payload"]["job_id"] == r.json()["data"]["id"]
        assert {"job.started", "job.progress", "job.finished"} <= seen
    wait_for_job(client, r.json()["data"]["id"])


def test_websocket_requires_auth_when_secured(secured):
    from starlette.websockets import WebSocketDisconnect

    with secured.websocket_connect(f"{API}/ws") as ws:
        ws.send_json({"type": "auth", "api_key": "viewer-key"})
        assert ws.receive_json()["type"] == "hello"
    with pytest.raises(WebSocketDisconnect) as exc, secured.websocket_connect(f"{API}/ws") as ws:
        ws.send_json({"type": "auth", "api_key": "nope"})
        ws.receive_json()
    assert exc.value.code == 4401


def test_cache_backends():
    m = MemoryCache(max_items=2)
    calls = []
    assert m.get_or_set("k", 60, lambda: calls.append(1) or {"v": 1}) == {"v": 1} and m.get_or_set("k", 60, lambda: {"v": 2}) == {"v": 1}
    m.set("expired", 1, ttl_s=-1)
    assert m.get("expired") is None
    m.set("a", 1, 60), m.set("b", 2, 60), m.set("c", 3, 60)
    assert sum(m.get(k) is not None for k in ("k", "a", "b", "c")) <= 2
    fakeredis = pytest.importorskip("fakeredis")
    r = RedisCache(fakeredis.FakeRedis())
    assert r.get_or_set("x", 60, lambda: {"a": [1, 2]}) == {"a": [1, 2]} and r.get("x") == {"a": [1, 2]}

    class Broken:
        def get(self, *_): raise ConnectionError
        def set(self, *_, **__): raise ConnectionError

    b = RedisCache(Broken())
    assert b.get_or_set("y", 5, lambda: 42) == 42  # degrades to computing, never raises
    assert create_cache("redis://127.0.0.1:1/0").name == "memory"
