import numpy as np
import pytest

from ml.core.provenance import DataKind
from ml.data.synthetic import ScenarioConfig, generate_scenario
from ml.pipeline.demo import run_demo_pipeline


@pytest.fixture(scope="module")
def result():
    return run_demo_pipeline()


def test_scenario_is_deterministic_and_labelled_synthetic():
    a, b = generate_scenario(), generate_scenario()
    assert np.array_equal(a.truth_fine["tp"], b.truth_fine["tp"])
    assert np.array_equal(a.ensemble_coarse["tp"], b.ensemble_coarse["tp"])
    assert a.data_kind == DataKind.SYNTHETIC_DEMO
    assert a.forecast_dataset().attrs["data_kind"] == "SYNTHETIC_DEMO"
    c = generate_scenario(ScenarioConfig(seed=8))
    assert not np.array_equal(a.truth_fine["tp"], c.truth_fine["tp"])


def test_scenario_shapes_and_physical_sanity():
    s = generate_scenario()
    t = len(s.lead_hours)
    assert s.truth_fine["tp"].shape == (t, 240, 240)
    assert s.forecast_coarse["tp"].shape == (t, 120, 120)
    assert s.ensemble_coarse["tp"].shape == (10, t, 120, 120)
    assert all(np.isfinite(v).all() for v in s.truth_fine.values())
    assert s.truth_fine["tp"].min() >= 0
    assert 90000 < s.truth_fine["msl"].min() < s.truth_fine["msl"].max() < 102000
    # coarse control is the exact block mean of fine truth (conservation by construction)
    from ml.core.grid import block_mean
    assert np.allclose(block_mean(s.truth_fine["tp"], 2), s.forecast_coarse["tp"], rtol=1e-5, atol=1e-4)
    # cyclonic circulation: intensification then filling after landfall
    v = [np.hypot(s.truth_fine["u10"][i], s.truth_fine["v10"][i]).max() for i in range(t)]
    assert max(v) > v[0] and v[-1] < max(v)


def test_pipeline_output_is_labelled_and_has_provenance(result):
    p = result.provenance
    assert p.data_kind == DataKind.SYNTHETIC_DEMO
    assert any("SYNTHETIC" in n for n in p.notes)
    assert p.pipeline_config_hash and p.dataset_id.startswith("synthetic-demo")
    assert p.checkpoint_sha256 is None  # no trained model exists


def test_primary_track_is_continuous_and_follows_the_synthetic_storm(result):
    tr = result.primary
    assert len(tr.observed_points) == len(result.lead_hours)
    assert result.tracking_eval["mean_error_vs_true_storm_centre_km"] < 100
    lats = [p.lat for p in tr.observed_points]
    assert lats[-1] > lats[0]  # moves north
    hind = result.tracking_eval["hindcast"]
    assert hind["kalman"][1] < hind["persistence"][1]


def test_ensemble_spread_grows_with_lead(result):
    r = [e.radius_km_p90 for e in result.envelopes if e]
    assert r[-1] > r[0]
    assert all(0.0 <= a <= 1.0 for a in result.member_agreement)
    assert all(np.all(np.abs(f) <= 1.0) for f in result.efi)


def test_downscaling_evaluation_is_real_and_shows_smoothing(result):
    rows = {r["method"]: r["metrics"] for r in result.downscaling_eval}
    assert set(rows) == {"nearest", "bilinear", "bicubic", "bicubic_conservative"}
    for m in rows.values():
        assert m["peak_error"]["mean"] < 0  # every interpolation underestimates the fine-scale peak
        assert np.isfinite(m["rmse"]["mean"]) and m["rmse"]["ci_low"] <= m["rmse"]["mean"] <= m["rmse"]["ci_high"]
    assert rows["bicubic_conservative"]["rmse"]["mean"] < rows["nearest"]["rmse"]["mean"]
    assert all(p.checks_passed for p in result.physics)
    assert all(a.shape == (len(result.lead_hours), 240, 240) and np.isfinite(a).all() for a in result.downscaled.values())


def test_risk_impact_and_disclaimer(result):
    assert result.risk.category in {"LOW", "MODERATE", "SEVERE"}
    assert "Not an official warning" in result.risk.disclaimer
    assert set(result.impact) == set(result.lead_hours)
    peak = max(result.impact.values(), key=lambda v: len(v["regions_risk"]))
    assert any(r["name"] == "Odisha" for r in peak["regions_risk"])
    for v in result.impact.values():
        g = v["geometries"]
        assert g["impact"].within(g["risk"]) and g["risk"].within(g["uncertainty"])


def test_pipeline_is_deterministic(result):
    again = run_demo_pipeline()
    assert [round(p.lat, 6) for p in again.primary.points] == [round(p.lat, 6) for p in result.primary.points]
    assert again.risk.score == result.risk.score
    assert again.provenance.pipeline_config_hash == result.provenance.pipeline_config_hash


def test_progress_callback_reports_monotonic_fractions():
    seen = []
    run_demo_pipeline(progress=lambda s, f: seen.append((s, f)))
    fr = [f for _, f in seen]
    assert fr == sorted(fr) and fr[-1] == 1.0 and seen[-1][0] == "done"
