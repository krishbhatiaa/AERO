import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ml.core.geometry import (
    EARTH_RADIUS_KM,
    bearing_deg,
    circle_ring,
    destination,
    from_local_xy,
    haversine_km,
    normalize_lon,
    to_local_xy,
)
from ml.core.grid import GridSpec, block_mean
from ml.core.provenance import DataKind, combine_kinds, config_hash
from ml.core.units import convert, geopotential_to_height, kelvin_to_celsius, metres_to_mm


def test_combine_kinds_takes_weakest():
    assert combine_kinds(DataKind.OBSERVED, DataKind.REANALYSIS) == DataKind.REANALYSIS
    assert combine_kinds(DataKind.FORECAST, DataKind.OBSERVED) == DataKind.FORECAST
    assert combine_kinds(DataKind.REANALYSIS, DataKind.SYNTHETIC_DEMO) == DataKind.SYNTHETIC_DEMO
    assert combine_kinds(DataKind.MODEL_PREDICTION, DataKind.FORECAST) == DataKind.MODEL_PREDICTION
    with pytest.raises(ValueError):
        combine_kinds()


def test_config_hash_is_stable_and_order_independent():
    assert config_hash({"a": 1, "b": 2}) == config_hash({"b": 2, "a": 1})
    assert config_hash({"a": 1}) != config_hash({"a": 2})


def test_haversine_known_distance():
    # Mumbai -> Delhi is roughly 1150 km great-circle
    d = float(haversine_km(19.076, 72.8777, 28.7041, 77.1025))
    assert 1100 < d < 1200
    assert float(haversine_km(10, 20, 10, 20)) == 0.0


@given(st.floats(-80, 80), st.floats(-179, 179), st.floats(0, 359), st.floats(1, 2000))
@settings(max_examples=60, deadline=None)
def test_destination_inverts_distance_and_bearing(lat, lon, brg, dist):
    lat2, lon2 = destination(lat, lon, brg, dist)
    assert float(haversine_km(lat, lon, lat2, lon2)) == pytest.approx(dist, rel=1e-6, abs=1e-6)
    assert float(bearing_deg(lat, lon, lat2, lon2)) == pytest.approx(brg % 360, abs=1e-4) or abs(
        ((float(bearing_deg(lat, lon, lat2, lon2)) - brg + 180) % 360) - 180) < 1e-4


@given(st.floats(-60, 60), st.floats(-170, 170), st.floats(-800, 800), st.floats(-800, 800))
@settings(max_examples=60, deadline=None)
def test_local_xy_roundtrip(lat0, lon0, x, y):
    lat, lon = from_local_xy(x, y, lat0, lon0)
    xx, yy = to_local_xy(lat, lon, lat0, lon0)
    assert float(xx) == pytest.approx(x, abs=1e-6)
    assert float(yy) == pytest.approx(y, abs=1e-6)


@given(st.floats(-1e4, 1e4))
def test_normalize_lon_wraps_into_range(lon):
    a = float(normalize_lon(lon))
    b = float(normalize_lon(lon, "0_360"))
    assert -180 <= a < 180
    assert 0 <= b < 360
    assert (a - lon) % 360 == pytest.approx(0, abs=1e-6) or (a - lon) % 360 == pytest.approx(360, abs=1e-6)


def test_circle_ring_is_closed_and_has_right_radius():
    ring = circle_ring(20.0, 85.0, 100.0, n=36)
    assert ring[0] == ring[-1]
    d = haversine_km(20.0, 85.0, np.array([p[1] for p in ring]), np.array([p[0] for p in ring]))
    assert np.allclose(d, 100.0, atol=1e-6)
    with pytest.raises(ValueError):
        circle_ring(0, 0, -1)


def test_global_grid_areas_sum_to_sphere_surface():
    g = GridSpec(-89.5, 0.5, 1.0, 1.0, 180, 360)
    assert g.is_global_lon
    assert g.cell_area_km2().sum() == pytest.approx(4 * np.pi * EARTH_RADIUS_KM**2, rel=1e-9)


def test_cell_area_shrinks_towards_the_pole_not_pixel_count():
    g = GridSpec(-89.5, 0.5, 1.0, 1.0, 180, 360)
    rows = g.row_area_km2()
    assert rows[90] > 10 * rows[0]


def test_refined_grid_is_aligned_with_coarse_cells():
    c = GridSpec(12.05, 80.05, 0.1, 0.1, 4, 4)
    f = c.refined(2)
    assert f.shape == (8, 8)
    assert f.bounds == pytest.approx(c.bounds)
    field = np.arange(64, dtype=float).reshape(8, 8)
    assert block_mean(field, 2).shape == (4, 4)
    with pytest.raises(ValueError):
        block_mean(np.zeros((5, 4)), 2)


def test_gridspec_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        GridSpec(0, 0, -1, 1, 3, 3)
    with pytest.raises(ValueError):
        GridSpec(89.9, 0, 1, 1, 5, 5)


def test_unit_conversions():
    assert float(kelvin_to_celsius(273.15)) == pytest.approx(0.0)
    assert float(metres_to_mm(0.0123)) == pytest.approx(12.3)
    assert float(geopotential_to_height(9.80665 * 1000)) == pytest.approx(1000.0)
    assert float(convert(1.0, "m s-1", "kt")) == pytest.approx(1.943844, rel=1e-6)
    assert float(convert(5.0, "mm", "mm")) == 5.0
    with pytest.raises(ValueError):
        convert(1.0, "furlong", "mm")
