import numpy as np
import pandas as pd
import pytest
import xarray as xr

from ml.anomaly.detectors import EFIStyleDetector, MLAnomalyDetector, PercentileDetector, Thresholds, ZScoreDetector
from ml.anomaly.masks import EXTREME, MODERATE, NORMAL, classify
from ml.climatology.service import ClimatologyConfig, InsufficientSamplesError, build_climatology
from ml.core.provenance import DataKind


def make_da(n_years=30, window=7, seed=0, shape=(4, 5)):
    rng = np.random.default_rng(seed)
    times = []
    for y in range(1991, 1991 + n_years):
        for d in range(-window, window + 1):
            times.append(pd.Timestamp(year=y, month=9, day=1) + pd.Timedelta(days=d))
    data = rng.normal(10.0, 2.0, size=(len(times), *shape))
    return xr.DataArray(data, dims=("time", "latitude", "longitude"),
                        coords={"time": times, "latitude": np.arange(shape[0]) * 1.0, "longitude": np.arange(shape[1]) * 1.0},
                        attrs={"units": "mm"})


from ml.climatology.service import target_dayofyear  # noqa: E402

DOY = target_dayofyear(pd.Timestamp(2001, 9, 1))


def test_climatology_matches_numpy_reference():
    da = make_da()
    cfg = ClimatologyConfig("x", (1991, 2020), DOY, 7, 100)
    c = build_climatology(da, cfg, DataKind.REANALYSIS)
    assert c.n_samples == 450
    ref = da.values
    assert np.allclose(c.mean, ref.mean(0))
    assert np.allclose(c.std, ref.std(0, ddof=1))
    assert np.allclose(c.quantile_at(0.5), np.quantile(ref, 0.5, axis=0))
    assert np.allclose(c.quantile_at(0.955), np.quantile(ref, 0.955, axis=0), atol=0.15)


def test_climatology_dask_equals_eager():
    da = make_da()
    cfg = ClimatologyConfig("x", (1991, 2020), DOY, 7, 100)
    a = build_climatology(da, cfg)
    b = build_climatology(da.chunk({"time": 50, "latitude": 2}), cfg)
    assert np.allclose(a.mean, b.mean) and np.allclose(a.quantiles, b.quantiles)


def test_period_is_configurable_and_enforced():
    da = make_da()
    c1 = build_climatology(da, ClimatologyConfig("x", (1991, 2000), DOY, 7, 100))
    assert c1.n_samples == 150
    with pytest.raises(InsufficientSamplesError):
        build_climatology(da, ClimatologyConfig("x", (1991, 1993), DOY, 7, 100))
    assert c1.digest() != build_climatology(da, ClimatologyConfig("x", (1991, 2020), DOY, 7, 100)).digest()


def test_seasonal_window_excludes_far_days():
    da = make_da(window=40)
    c = build_climatology(da, ClimatologyConfig("x", (1991, 2020), DOY, 7, 100))
    assert c.n_samples == 30 * 15


@pytest.fixture(scope="module")
def clim():
    return build_climatology(make_da(seed=3), ClimatologyConfig("x", (1991, 2020), DOY, 7, 100))


def test_zscore_definition(clim):
    x = clim.mean + 3.0 * clim.std
    z = ZScoreDetector().score(x, clim)
    assert np.allclose(z, 3.0)


def test_percentile_score_is_monotonic_and_bounded(clim):
    det = PercentileDetector()
    xs = np.linspace(-5, 40, 200)
    scores = np.array([det.score(np.full(clim.mean.shape, v), clim)[0, 0] for v in xs])
    assert np.all(np.diff(scores) >= -1e-12)
    assert scores.min() >= 0 and scores.max() <= 1.0
    assert scores[-1] > 0.99
    med = det.score(clim.quantile_at(0.5), clim)
    assert np.allclose(med, 0.5, atol=0.03)


def test_percentile_nan_stays_nan(clim):
    x = clim.mean.copy()
    x[0, 0] = np.nan
    out = PercentileDetector().score(x, clim)
    assert np.isnan(out[0, 0]) and np.isfinite(out[1, 1])


def test_efi_extremes_and_neutral_case(clim):
    det = EFIStyleDetector()
    rng = np.random.default_rng(1)
    n = clim.mean.shape
    sample = rng.normal(10.0, 2.0, size=(51, *n))  # ensemble drawn from the climate itself
    assert abs(det.score(sample, clim).mean()) < 0.1
    above = np.full((20, *n), 100.0)
    below = np.full((20, *n), -100.0)
    assert det.score(above, clim).min() > 0.95
    assert det.score(below, clim).max() < -0.95
    assert np.all(np.abs(det.score(sample, clim)) <= 1.0)


def test_efi_single_field_is_degenerate_ensemble(clim):
    x = np.full(clim.mean.shape, 100.0)
    assert np.allclose(EFIStyleDetector().score(x, clim), EFIStyleDetector().score(x[None], clim))


def test_masks_three_classes_and_nan_never_extreme():
    thr = Thresholds(2.0, 3.0)
    s = np.array([0.0, 1.9, 2.0, 2.9, 3.0, 9.0, np.nan, -5.0])
    m = classify(s, thr)
    assert list(m) == [NORMAL, NORMAL, MODERATE, MODERATE, EXTREME, EXTREME, NORMAL, NORMAL]
    assert classify(np.array([-5.0]), thr, two_sided=True)[0] == EXTREME
    with pytest.raises(ValueError):
        Thresholds(3.0, 2.0)


def test_ml_detector_wraps_callable(clim):
    det = MLAnomalyDetector(lambda f, c: (f - c.mean) / 10.0, Thresholds(0.1, 0.3))
    out = det.score(clim.mean + 5.0, clim)
    assert np.allclose(out, 0.5)
    bad = MLAnomalyDetector(lambda f, c: np.zeros(3), Thresholds(0.1, 0.3))
    with pytest.raises(ValueError):
        bad.score(clim.mean, clim)
