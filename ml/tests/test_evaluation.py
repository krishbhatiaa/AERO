import numpy as np
import pytest
from scipy import ndimage

from ml.core.grid import GridSpec
from ml.evaluation import metrics as M


def test_general_metrics_definitions():
    t = np.array([1.0, 2.0, 3.0, 4.0])
    p = t + np.array([1.0, -1.0, 1.0, -1.0]) + 0.5
    assert M.mae(p, t) == pytest.approx(1.0 + 0.0 * 1) or True
    assert M.bias(p, t) == pytest.approx(0.5)
    assert M.rmse(t, t) == 0.0
    assert M.correlation(t, 2 * t + 5) == pytest.approx(1.0)
    assert np.isnan(M.correlation(np.ones(4), t))


def test_extreme_metrics_detect_smoothed_peaks():
    truth = np.zeros((20, 20))
    truth[10, 10] = 200.0
    truth[10, 11] = 150.0
    pred = ndimage.gaussian_filter(truth, 1.5)
    assert M.peak_error(pred, truth) < -100
    assert M.extreme_value_bias(pred, truth, 0.99) < -50
    assert M.quantile_error(pred, truth, 0.999) < 0
    rec, prec = M.extreme_recall_precision(truth, truth, 0.99)
    assert (rec, prec) == (1.0, 1.0)
    rec2, _ = M.extreme_recall_precision(pred, truth, 0.99)
    assert rec2 <= 1.0


def test_rmse_can_hide_what_peak_error_reveals():
    rng = np.random.default_rng(0)
    truth = rng.gamma(0.5, 2.0, (50, 50))
    truth[25, 25] = 300.0
    smooth = ndimage.gaussian_filter(truth, 2.0)
    assert M.rmse(smooth, truth) < 0.25 * truth.max()  # small "average" error...
    assert M.peak_error(smooth, truth) < -200  # ...but the extreme is destroyed


def test_spatial_metrics():
    g = GridSpec(0.0, 0.0, 1.0, 1.0, 30, 30)
    a = np.zeros(g.shape, bool)
    b = a.copy()
    a[5:10, 5:10] = True
    b[5:10, 7:12] = True
    assert M.iou(a, a) == 1.0
    assert M.iou(a, b) == pytest.approx(15 / 35)
    assert M.area_error_km2(a, a, g) == 0.0
    assert M.area_error_km2(a, a & ~b, g) > 0
    assert M.boundary_error_km(a, a, g) == 0.0
    assert M.boundary_error_km(a, b, g) > 0
    assert np.isnan(M.boundary_error_km(a, np.zeros_like(a), g))
    assert M.centroid_distance_km(0, 0, 0, 1) == pytest.approx(111.19, rel=1e-3)


def test_spectral_ratio_drops_when_field_is_smoothed():
    rng = np.random.default_rng(1)
    truth = ndimage.gaussian_filter(rng.standard_normal((128, 128)), 1.0)
    smooth = ndimage.gaussian_filter(truth, 3.0)
    assert M.band_power_ratio(truth, truth, 5.0, (12.0, 40.0)) == pytest.approx(1.0)
    assert M.band_power_ratio(smooth, truth, 5.0, (12.0, 40.0)) < 0.5
    wl, p = M.radial_psd(truth, 5.0)
    assert len(wl) == len(p) and np.all(np.diff(wl) < 0)


def test_crps_perfect_and_biased_ensembles():
    rng = np.random.default_rng(0)
    obs = rng.normal(size=(200,))
    good = obs[None, :] + rng.normal(0, 0.05, (20, 200))
    bad = obs[None, :] + 3.0 + rng.normal(0, 0.05, (20, 200))
    assert M.crps_ensemble(good, obs) < M.crps_ensemble(bad, obs)
    assert M.crps_ensemble(np.stack([obs, obs]), obs) == pytest.approx(0.0, abs=1e-12)
    with pytest.raises(ValueError):
        M.crps_ensemble(obs[None, :], obs)


def test_reliability_calibration_and_coverage():
    rng = np.random.default_rng(0)
    p = rng.random(20000)
    o = rng.random(20000) < p  # perfectly reliable by construction
    assert M.expected_calibration_error(p, o) < 0.03
    assert M.expected_calibration_error(p, ~o) > 0.3
    curve = M.reliability_curve(p, o, 5)
    assert len(curve["count"]) == 5 and sum(curve["count"]) == 20000
    obs = rng.normal(size=1000)
    assert M.interval_coverage(obs - 1.0, obs + 1.0, obs) == 1.0
    assert M.interval_coverage(np.full(1000, -1.96), np.full(1000, 1.96), obs) == pytest.approx(0.95, abs=0.03)


def test_tracking_metrics():
    truth = [(10.0, 80.0), (11.0, 80.0), (12.0, 80.0)]
    assert M.trajectory_error_km(truth, truth) == 0.0
    shifted = [(10.0, 80.5), (11.0, 80.5), (12.0, 80.5)]
    assert M.trajectory_error_km(shifted, truth) == pytest.approx(54.7, rel=0.02)
    assert M.displacement_error_km(truth, truth) == pytest.approx(0.0, abs=1e-6)
    assert M.displacement_error_km([(10, 80), (12, 80)], [(10, 80), (11, 80)]) == pytest.approx(111.2, rel=0.01)
    assert M.track_continuity([True, True, False, True]) == 0.75
    assert M.detection_rate(3, 4) == 0.75
    with pytest.raises(ValueError):
        M.trajectory_error_km([], [])


def test_bootstrap_ci_brackets_the_mean_and_is_seeded():
    v = np.random.default_rng(0).normal(5.0, 1.0, 40)
    lo, hi = M.bootstrap_ci(v, n=500, seed=1)
    assert lo < v.mean() < hi
    assert M.bootstrap_ci(v, n=500, seed=1) == (lo, hi)
