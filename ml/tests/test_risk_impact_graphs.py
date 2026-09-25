import json

import numpy as np
import pytest
from shapely.geometry import Polygon, box, shape

from ml.core.grid import GridSpec
from ml.gnn.graphs import (
    grid_to_mesh_edges,
    icosahedral_mesh,
    knn_graph,
    latlon_grid_graph,
    latlon_to_xyz,
    radius_graph,
)
from ml.impact.geometry import R68_OVER_R95, Region, RegionIndex, area_km2, buffer_km, build_impact_geometries
from ml.risk.engine import RiskEngine, RiskInputs
from ml.uncertainty.ensemble import confidence_class, ensemble_summary, mean_position, track_envelope


def inputs(**kw):
    base = dict(event_type="EXTREME_RAINFALL", peak_intensity=120.0, probability=0.9, duration_h=24.0, area_km2=8000.0,
                forecast_horizon_h=24.0, uncertainty_radius_km=50.0, member_agreement=0.9)
    base.update(kw)
    return RiskInputs(**base)


def test_risk_categories_are_monotonic_in_each_driver():
    eng = RiskEngine()
    scores = [eng.assess(inputs(peak_intensity=x)).score for x in (10, 50, 100, 150, 250)]
    assert scores == sorted(scores)
    scores = [eng.assess(inputs(probability=p)).score for p in (0.1, 0.4, 0.7, 1.0)]
    assert scores == sorted(scores)
    assert eng.assess(inputs(peak_intensity=5, area_km2=100, duration_h=1)).category == "LOW"
    assert eng.assess(inputs(peak_intensity=500, area_km2=90000, duration_h=96, probability=1.0)).category == "SEVERE"


def test_risk_output_is_explained_and_not_official():
    a = RiskEngine().assess(inputs())
    assert a.category in {"LOW", "MODERATE", "SEVERE"}
    assert len(a.rationale) == 5 and "Not an official warning" in a.disclaimer
    assert set(a.components) == {"intensity", "area", "duration"}


def test_uncertainty_changes_confidence_not_category():
    eng = RiskEngine()
    tight = eng.assess(inputs(uncertainty_radius_km=20, member_agreement=0.95))
    loose = eng.assess(inputs(uncertainty_radius_km=400, member_agreement=0.2))
    assert tight.category == loose.category and tight.score == loose.score
    assert tight.confidence == "HIGH" and loose.confidence == "LOW"


def test_risk_validation_errors():
    eng = RiskEngine()
    with pytest.raises(ValueError):
        eng.assess(inputs(probability=1.5))
    with pytest.raises(ValueError):
        eng.assess(inputs(event_type="TSUNAMI"))
    with pytest.raises(ValueError):
        RiskEngine({"weights": {"a": 0.5, "b": 0.6}, "scales": {}, "category_thresholds": {}, "probability_exponent": 1, "disclaimer": ""})


def test_confidence_class_boundaries():
    assert confidence_class(0.9, 50) == "HIGH"
    assert confidence_class(0.6, 100) == "MEDIUM"
    assert confidence_class(0.9, 500) == "LOW"
    assert confidence_class(0.1, 10) == "LOW"


def test_ensemble_summary_and_envelope():
    rng = np.random.default_rng(0)
    m = rng.normal(10, 2, (30, 5, 5))
    s = ensemble_summary(m, exceed_threshold=10.0)
    assert set(s) >= {"mean", "median", "std", "p10", "p90", "p95", "p99", "exceed_prob"}
    assert np.all(s["p90"] >= s["p10"]) and np.all((s["exceed_prob"] >= 0) & (s["exceed_prob"] <= 1))
    with pytest.raises(ValueError):
        ensemble_summary(m[:1])
    pos = np.array([[20.0, 86.0], [20.5, 86.5], [19.5, 85.5], [20.0, 86.0]])
    env = track_envelope(pos)
    assert 19.9 < env.mean_lat < 20.1 and env.radius_km_p90 > 0 and env.n_members == 4
    lat, lon = mean_position(np.array([[0.0, 179.0], [0.0, -179.0]]))
    assert abs(abs(lon) - 180) < 1e-6


def test_impact_polygons_are_nested_and_sized_correctly():
    g = build_impact_geometries((20.0, 86.0), 50.0, 100.0)
    assert set(g) == {"impact", "risk", "uncertainty"}
    assert g["impact"].within(g["risk"]) and g["risk"].within(g["uncertainty"])
    assert area_km2(g["impact"]) == pytest.approx(np.pi * 50.0**2, rel=0.01)
    assert area_km2(g["uncertainty"]) == pytest.approx(np.pi * 150.0**2, rel=0.02)
    assert area_km2(g["risk"]) == pytest.approx(np.pi * (50 + 100 * R68_OVER_R95) ** 2, rel=0.02)
    fp = box(85, 19, 86, 20)
    g2 = build_impact_geometries((19.5, 85.5), 0.0, 30.0, footprint=fp)
    assert g2["impact"] is fp and g2["uncertainty"].contains(fp)
    with pytest.raises(ValueError):
        buffer_km(fp, -1.0, 19.5, 85.5)


def test_region_intersection_areas_and_fractions():
    a = Region("state:A", "A", "A", "state", box(85.0, 19.0, 86.0, 21.0))
    b = Region("state:B", "B", "B", "state", box(86.0, 19.0, 87.0, 21.0))
    idx = RegionIndex([a, b])
    poly = box(85.5, 19.5, 86.25, 20.5)
    out = idx.intersect(poly)
    assert [r["name"] for r in out] == ["A", "B"]
    assert out[0]["intersect_area_km2"] > out[1]["intersect_area_km2"]
    assert sum(r["fraction_of_polygon"] for r in out) == pytest.approx(1.0, abs=1e-6)
    assert idx.intersect(box(0, 0, 1, 1)) == []
    assert RegionIndex([]).intersect(poly) == []


def test_region_index_loads_bundled_geojson_and_finds_odisha():
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "sample_data" / "boundaries" / "india_states_domain.geojson"
    idx = RegionIndex.from_geojson(path)
    names = {r["name"] for r in idx.intersect(Polygon([(86.5, 20.5), (87.0, 20.5), (87.0, 21.0), (86.5, 21.0)]))}
    assert "Odisha" in names
    feats = json.loads(path.read_text())["features"]
    assert all(shape(f["geometry"]).is_valid for f in feats)


def test_icosahedral_mesh_counts_match_theory_and_lie_on_sphere():
    for level in range(4):
        g = icosahedral_mesh(level)
        assert g.n_nodes == 10 * 4**level + 2
        assert g.n_edges == 2 * 30 * 4**level
        assert np.allclose(np.linalg.norm(g.xyz, axis=1), 1.0)
    assert icosahedral_mesh(6).n_nodes == 40962
    with pytest.raises(ValueError):
        icosahedral_mesh(-1)


def test_icosahedral_edge_lengths_are_roughly_uniform():
    g = icosahedral_mesh(3)
    d = g.edge_attr[:, 0]
    assert d.max() / d.min() < 1.6


def test_knn_and_radius_graphs():
    rng = np.random.default_rng(0)
    ll = np.stack([rng.uniform(10, 25, 50), rng.uniform(80, 95, 50)], axis=1)
    g = knn_graph(ll, 4)
    assert g.edge_index.shape == (2, 200) and g.edge_attr.shape == (200, 3)
    assert not np.any(g.edge_index[0] == g.edge_index[1])
    r = radius_graph(ll, 300.0)
    assert np.all(r.edge_attr[:, 0] <= 300.0 + 1e-6)
    assert r.n_edges % 2 == 0
    with pytest.raises(ValueError):
        knn_graph(ll, 0)


def test_grid_graph_periodic_longitude_and_bipartite_wiring():
    g = GridSpec(-89.5, 0.5, 1.0, 1.0, 180, 360)
    gg = latlon_grid_graph(GridSpec(-1.5, 0.5, 1.0, 1.0, 3, 360))
    assert gg.n_nodes == 3 * 360
    assert (0 * 360 + 359) in gg.edge_index[1][gg.edge_index[0] == 0]  # node (0,0) links to (0,359)
    small = GridSpec(0.0, 0.0, 1.0, 1.0, 3, 3)
    assert latlon_grid_graph(small).n_edges == 40  # 8-neighbour count on a 3x3 grid
    mesh = icosahedral_mesh(2)
    lat, lon = np.meshgrid(g.lats[::30], g.lons[::30], indexing="ij")
    ei, attr = grid_to_mesh_edges(np.stack([lat.ravel(), lon.ravel()], 1), mesh, k=3)
    assert ei.shape[0] == 2 and ei.shape[1] == 3 * lat.size and attr.shape == (ei.shape[1], 3)
    assert np.allclose(np.linalg.norm(latlon_to_xyz(np.array([10.0]), np.array([20.0])), axis=1), 1.0)
