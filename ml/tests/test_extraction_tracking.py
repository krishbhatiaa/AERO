import numpy as np
import pytest
from shapely.geometry import box

from ml.core.geometry import EARTH_RADIUS_KM, from_local_xy
from ml.core.grid import GridSpec
from ml.extraction.regions import ExtractionConfig, extract_regions
from ml.tracking.hindcast import hindcast_extrapolation_errors
from ml.tracking.kalman import ConstantVelocityKalman
from ml.tracking.tracker import RegionTracker, TrackerConfig

G = GridSpec(0.0, 0.0, 1.0, 1.0, 40, 60)
NOFILTER = ExtractionConfig(min_area_km2=1.0, closing_iterations=0)


def blob(cy, cx, h=3, w=3, val=3.0, grid=G):
    s = np.zeros(grid.shape)
    s[cy : cy + h, cx : cx + w] = val
    return s


def test_region_area_uses_spherical_cell_areas_not_pixel_counts():
    s = blob(5, 5, 4, 4)
    regions, diag = extract_regions(s, G, 1.0, NOFILTER)
    assert len(regions) == 1 and diag["kept"] == 1
    expected = G.cell_area_km2()[5:9, 5:9].sum()
    assert regions[0].area_km2 == pytest.approx(expected)
    assert regions[0].n_cells == 16
    assert regions[0].max_score == 3.0


def test_rectangle_perimeter_and_compactness():
    r = extract_regions(blob(10, 10, 2, 3), G, 1.0, NOFILTER)[0][0]
    ns = EARTH_RADIUS_KM * np.radians(1.0)
    lat_edge = lambda lat: EARTH_RADIUS_KM * np.cos(np.radians(lat)) * np.radians(1.0)  # noqa: E731
    expected = 2 * ns * 2 + lat_edge(10) * 3 + lat_edge(11) * 3
    assert r.perimeter_km == pytest.approx(expected, rel=1e-9)
    assert 0 < r.compactness <= 1.0


def test_two_blobs_and_small_component_rejection_is_reported():
    s = blob(5, 5, 4, 4) + blob(30, 40, 1, 1)
    regions, diag = extract_regions(s, G, 1.0, ExtractionConfig(min_area_km2=50000.0, closing_iterations=0))
    assert len(regions) == 1
    assert diag["rejected_too_small"] == 1 and diag["components"] == 2


def test_8_connectivity_joins_diagonals_4_does_not():
    s = np.zeros(G.shape)
    s[5, 5] = s[6, 6] = 3.0
    assert len(extract_regions(s, G, 1.0, ExtractionConfig(1.0, 0, 0, 8))[0]) == 1
    assert len(extract_regions(s, G, 1.0, ExtractionConfig(1.0, 0, 0, 4))[0]) == 2


def test_region_merges_across_longitude_seam_on_global_grid():
    g = GridSpec(-89.5, 0.5, 1.0, 1.0, 180, 360)
    s = np.zeros(g.shape)
    s[90:93, 0:2] = 1.0
    s[90:93, -2:] = 1.0
    regions, _ = extract_regions(s, g, 0.5, NOFILTER)
    assert len(regions) == 1
    assert abs(regions[0].centroid_lon) < 1e-6 or abs(abs(regions[0].centroid_lon) - 360) < 1e-6


def test_closing_fills_single_cell_hole():
    s = blob(5, 5, 5, 5)
    s[7, 7] = 0.0
    with_close, _ = extract_regions(s, G, 1.0, ExtractionConfig(1.0, 1, 0, 8))
    no_close, _ = extract_regions(s, G, 1.0, ExtractionConfig(1.0, 0, 0, 8))
    assert with_close[0].n_cells == 25 and no_close[0].n_cells == 24


def test_shape_mismatch_raises():
    with pytest.raises(ValueError):
        extract_regions(np.zeros((3, 3)), G, 1.0)


def moving_frames(n=8, dx_cells=1, dy_cells=0, val=3.0):
    frames = []
    for k in range(n):
        s = blob(15 + dy_cells * k, 5 + dx_cells * 2 * k, 4, 4, val + 0.1 * k)
        regions, _ = extract_regions(s, G, 1.0, NOFILTER, intensity=s * 10)
        frames.append((6.0 * k, regions))
    return frames


def test_tracker_recovers_constant_velocity():
    tr = RegionTracker(TrackerConfig()).run(moving_frames(dx_cells=1))
    assert len(tr) == 1
    t = tr[0]
    assert len(t.observed_points) == 8
    # blob moves 2 cells (=2 deg lon ~ 219 km at the equator) per 6 h => ~37 km/h heading east (090)
    assert t.last.speed_kmh == pytest.approx(2 * 111.19 / 6.0, rel=0.1)
    assert t.last.bearing_deg == pytest.approx(90.0, abs=3.0)
    assert t.last.uncertainty_radius_km < t.points[0].uncertainty_radius_km + 1


def test_tracker_coasts_then_reacquires_and_terminates():
    frames = moving_frames(n=6, dx_cells=1)
    frames[3] = (frames[3][0], [])  # missed detection
    t = RegionTracker(TrackerConfig(max_missed=1)).run(frames)
    assert len(t) == 1
    assert [p.observed for p in t[0].points] == [True, True, True, False, True, True]
    frames2 = moving_frames(n=6, dx_cells=1)
    frames2[3] = (frames2[3][0], [])
    frames2[4] = (frames2[4][0], [])
    t2 = RegionTracker(TrackerConfig(max_missed=1)).run(frames2)
    assert not t2[0].active or len(t2) >= 2


def test_tracker_rejects_jump_beyond_gate_and_starts_new_track():
    a, _ = extract_regions(blob(5, 5), G, 1.0, NOFILTER)
    b, _ = extract_regions(blob(30, 50), G, 1.0, NOFILTER)
    tracks = RegionTracker(TrackerConfig(gate_km=300)).run([(0.0, a), (6.0, b)])
    assert len(tracks) == 2


def test_tracker_marks_split_with_parent():
    big, _ = extract_regions(blob(10, 10, 6, 6), G, 1.0, NOFILTER)
    s = blob(10, 10, 3, 3) + blob(10, 14, 3, 3)
    parts, _ = extract_regions(s, G, 1.0, ExtractionConfig(1.0, 0, 0, 4))
    tracks = RegionTracker(TrackerConfig()).run([(0.0, big), (6.0, parts)])
    assert len(tracks) == 2
    assert any(t.parent_id is not None for t in tracks)


def test_kalman_converges_to_true_velocity():
    kf = ConstantVelocityKalman(0.0, 0.0, 5.0, 0.5, 30.0)
    rng = np.random.default_rng(0)
    for k in range(1, 15):
        kf.predict(1.0)
        kf.update(20.0 * k + rng.normal(0, 3), 10.0 * k + rng.normal(0, 3))
    assert kf.x[2] == pytest.approx(20.0, abs=3.0)
    assert kf.x[3] == pytest.approx(10.0, abs=3.0)
    assert kf.position_radius_km() < 30.0


def test_extrapolation_grows_uncertainty():
    t = RegionTracker(TrackerConfig()).run(moving_frames())[0]
    pts = t.extrapolate(t.last.time_h, [54.0, 60.0, 72.0])
    assert pts[0]["uncertainty_radius_km"] < pts[1]["uncertainty_radius_km"] < pts[2]["uncertainty_radius_km"]
    assert pts[-1]["lon"] > t.last.lon


def test_kalman_hindcast_beats_persistence_for_steady_motion():
    t = RegionTracker(TrackerConfig()).run(moving_frames(n=9))[0]
    e = hindcast_extrapolation_errors(t, TrackerConfig(), 3)
    for h in (1, 2, 3):
        assert e["kalman"][h] < e["persistence"][h]


def test_local_xy_used_by_tracker_is_consistent():
    lat, lon = from_local_xy(100.0, 0.0, 10.0, 80.0)
    assert float(lat) == pytest.approx(10.0, abs=0.01) and float(lon) > 80.0
    assert box(0, 0, 1, 1).area == 1.0
