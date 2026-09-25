import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.extra import numpy as hnp

from ml.core.grid import GridSpec, block_mean
from ml.downscaling.baseline import BaselineDownscaler, upsample
from ml.losses import reference as L
from ml.physics.conservation import block_weighted_mean, conservation_residual, enforce_block_mean
from ml.physics.diagnostics import horizontal_divergence, physics_report
from ml.physics.saturation import saturation_specific_humidity, saturation_vapor_pressure_hpa, saturation_violation_fraction

C = GridSpec(10.05, 80.05, 0.1, 0.1, 12, 14)
F = C.refined(2)


def test_bilinear_and_bicubic_reproduce_a_linear_field_exactly():
    lon2d, lat2d = np.meshgrid(C.lons, C.lats)
    coarse = 3.0 * lat2d + 2.0 * lon2d + 1.0
    lon_f, lat_f = np.meshgrid(F.lons, F.lats)
    truth = 3.0 * lat_f + 2.0 * lon_f + 1.0
    lin = upsample(coarse, C, F, 1)
    assert np.allclose(lin[1:-1, 1:-1], truth[1:-1, 1:-1], atol=1e-8)  # exact except the clamped outer half-cell
    inner = (slice(8, -8), slice(8, -8))  # cubic splines have a boundary layer (edge-clamped)
    assert np.allclose(upsample(coarse, C, F, 3)[inner], truth[inner], atol=2e-3)


def test_nearest_replicates_blocks():
    coarse = np.arange(C.nlat * C.nlon, dtype=float).reshape(C.shape)
    up = BaselineDownscaler("nearest", nonneg=False).downscale(coarse, C, F)
    assert np.array_equal(up[::2, ::2], coarse) and np.array_equal(up[1::2, 1::2], coarse)


def test_conservative_method_preserves_block_means_and_nonnegativity():
    rng = np.random.default_rng(0)
    coarse = rng.gamma(0.5, 10.0, C.shape)
    fine = BaselineDownscaler("bicubic_conservative").downscale(coarse, C, F)
    assert fine.min() >= 0.0
    assert np.allclose(block_mean(fine, 2), coarse, rtol=1e-9, atol=1e-9)


def test_plain_bicubic_can_break_conservation_that_projection_repairs():
    coarse = np.zeros(C.shape)
    coarse[5:7, 5:7] = 100.0
    plain = BaselineDownscaler("bicubic").downscale(coarse, C, F)
    fixed = BaselineDownscaler("bicubic_conservative").downscale(coarse, C, F)
    assert conservation_residual(plain, coarse, 2)["max_abs"] > 1e-3
    assert conservation_residual(fixed, coarse, 2)["max_abs"] < 1e-9


def test_unknown_method_and_shape_errors():
    with pytest.raises(ValueError):
        BaselineDownscaler("magic")
    with pytest.raises(ValueError):
        upsample(np.zeros((3, 3)), C, F, 1)


@given(hnp.arrays(np.float64, (4, 6), elements=st.floats(0, 500)), hnp.arrays(np.float64, (2, 3), elements=st.floats(0, 500)))
@settings(max_examples=50, deadline=None)
def test_conservation_projection_is_exact_and_idempotent(fine, coarse):
    out = enforce_block_mean(fine, coarse, 2)
    assert np.allclose(block_mean(out, 2), coarse, atol=1e-7)
    assert out.min() >= 0
    again = enforce_block_mean(out, coarse, 2)
    assert np.allclose(again, out, atol=1e-7)


def test_additive_mode_and_weights_and_errors():
    fine = np.ones((4, 4))
    coarse = np.full((2, 2), 3.0)
    assert np.allclose(enforce_block_mean(fine, coarse, 2, mode="additive"), 3.0)
    w = np.tile(np.array([[1.0], [3.0], [1.0], [3.0]]), (1, 4))
    f2 = np.array([[0.0] * 4, [4.0] * 4, [0.0] * 4, [4.0] * 4])
    assert np.allclose(block_weighted_mean(f2, 2, w), 3.0)
    with pytest.raises(ValueError):
        enforce_block_mean(fine, coarse, 3)
    with pytest.raises(ValueError):
        enforce_block_mean(fine, coarse, 2, mode="bogus")


def test_bolton_saturation_matches_metpy_and_known_value():
    e20 = float(saturation_vapor_pressure_hpa(20.0))
    assert e20 == pytest.approx(23.37, abs=0.05)  # ~23.4 hPa at 20 degC
    mp = pytest.importorskip("metpy.calc")
    units = pytest.importorskip("metpy.units").units
    t = np.array([-20.0, 0.0, 15.0, 30.0])
    ref = mp.saturation_vapor_pressure(t * units.degC).to("hPa").magnitude
    assert np.allclose(saturation_vapor_pressure_hpa(t), ref, rtol=5e-3)


def test_saturation_specific_humidity_and_violation_fraction():
    qs = float(saturation_specific_humidity(30.0, 1000.0))
    assert 0.025 < qs < 0.030
    q = np.array([0.5 * qs, 2.0 * qs])
    assert saturation_violation_fraction(q, np.full(2, 30.0), np.full(2, 1000.0)) == 0.5


def test_divergence_of_analytic_fields():
    lon2d, lat2d = np.meshgrid(C.lons, C.lats)
    r = 6371008.8
    a = 2e-5
    u = a * np.radians(lon2d - 85.0) * r * np.cos(np.radians(lat2d))
    assert np.allclose(horizontal_divergence(u, np.zeros_like(u), C), a, rtol=1e-6)
    assert np.allclose(horizontal_divergence(np.full(C.shape, 7.0), np.zeros(C.shape), C), 0.0, atol=1e-12)
    # uniform meridional wind on the sphere is NOT divergence-free: div = -v tan(phi)/R
    v = np.full(C.shape, 10.0)
    expected = -10.0 * np.tan(np.radians(lat2d)) / r
    assert np.allclose(horizontal_divergence(np.zeros(C.shape), v, C)[1:-1], expected[1:-1], rtol=2e-3)


def test_physics_report_flags_violations():
    coarse = np.full(C.shape, 5.0)
    good = np.full(F.shape, 5.0)
    assert physics_report(good, coarse, 2).checks_passed
    bad = good.copy()
    bad[0, 0] = -1.0
    rep = physics_report(bad, coarse, 2)
    assert rep.nonneg_violation_fraction > 0 and not rep.checks_passed
    with_wind = physics_report(good, coarse, 2, np.zeros(C.shape), np.zeros(C.shape), C)
    assert with_wind.wind_divergence_max_abs_s1 == 0.0


def test_extreme_weighted_loss_penalises_missed_peak_more_than_ordinary_error():
    # actual 200 mm predicted 80 mm vs ordinary value 20 mm predicted 20 - 120 (same absolute error)
    peak = L.extreme_weighted_loss(np.array([80.0]), np.array([200.0]), threshold=50.0, scale=50.0, alpha=1.0, beta=1.0)
    ordinary = L.extreme_weighted_loss(np.array([-100.0]), np.array([20.0]), threshold=50.0, scale=50.0, alpha=1.0, beta=1.0)
    assert L.mse(np.array([80.0]), np.array([200.0])) == L.mse(np.array([-100.0]), np.array([20.0]))
    assert peak == pytest.approx(4.0 * ordinary)
    assert L.extreme_weighted_loss(np.array([1.0]), np.array([1.0]), 50.0, 50.0) == 0.0


def test_basic_losses_definitions():
    p, t = np.array([1.0, 2.0, 6.0]), np.array([1.0, 4.0, 2.0])
    assert L.mse(p, t) == pytest.approx((0 + 4 + 16) / 3)
    assert L.mae(p, t) == pytest.approx(2.0)
    assert L.huber(p, t, delta=1.0) == pytest.approx((0 + 1.5 + 3.5) / 3)
    assert L.quantile_loss(np.array([0.0]), np.array([1.0]), 0.9) == pytest.approx(0.9)
    assert L.quantile_loss(np.array([1.0]), np.array([0.0]), 0.9) == pytest.approx(0.1)
    for bad in (0.0, 1.0):
        with pytest.raises(ValueError):
            L.quantile_loss(p, t, bad)
    with pytest.raises(ValueError):
        L.extreme_weights(t, 1.0, 0.0)
    with pytest.raises(ValueError):
        L.extreme_weighted_loss(p, t, 1.0, 1.0, base="nope")
    for base in ("mae", "huber"):
        assert L.extreme_weighted_loss(p, t, 100.0, 1.0, base=base) > 0
