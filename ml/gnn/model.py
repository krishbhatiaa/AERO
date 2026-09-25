"""GNN-based event tracker using Message Passing Neural Networks.

Builds graphs from anomaly region detections, computes association costs via a GNN, and
uses Hungarian assignment for final matching. Falls back to the classical tracker when
PyTorch/torch_geometric are not installed.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from scipy.optimize import linear_sum_assignment

from ml.core.geometry import bearing_deg, from_local_xy, haversine_km, to_local_xy
from ml.extraction.regions import AnomalyRegion
from ml.gnn.graphs import Graph, radius_graph
from ml.tracking.kalman import ConstantVelocityKalman
from ml.tracking.tracker import Track, TrackerConfig, TrackPoint

if TYPE_CHECKING:
    pass

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

try:
    from torch_geometric.nn import MessagePassing

    HAS_PYG = True
except ImportError:
    HAS_PYG = False

_BIG = 1e6

_NODE_FEATURE_DIM = 6
_EDGE_FEATURE_DIM = 3


class EdgeConv(MessagePassing):
    """Message passing layer with edge features."""

    def __init__(self, node_dim: int, edge_dim: int) -> None:
        super().__init__(aggr="mean")
        self.mlp = nn.Sequential(
            nn.Linear(node_dim * 2 + edge_dim, node_dim),
            nn.ReLU(),
            nn.Linear(node_dim, node_dim),
        )

    def forward(self, x: torch.Tensor, edge_index: torch.Tensor, edge_attr: torch.Tensor) -> torch.Tensor:
        return self.propagate(edge_index, x=x, edge_attr=edge_attr)

    def message(self, x_i: torch.Tensor, x_j: torch.Tensor, edge_attr: torch.Tensor) -> torch.Tensor:
        return self.mlp(torch.cat([x_i, x_j, edge_attr], dim=-1))


class AssociationGNN(nn.Module):
    """GNN that computes per-node embeddings for association scoring."""

    def __init__(self, node_dim: int = _NODE_FEATURE_DIM, edge_dim: int = _EDGE_FEATURE_DIM, hidden: int = 64, n_layers: int = 3) -> None:
        super().__init__()
        self.input_proj = nn.Linear(node_dim, hidden)
        self.layers = nn.ModuleList([EdgeConv(hidden, edge_dim) for _ in range(n_layers)])
        self.output_proj = nn.Linear(hidden, hidden)

    def forward(self, x: torch.Tensor, edge_index: torch.Tensor, edge_attr: torch.Tensor) -> torch.Tensor:
        h = F.relu(self.input_proj(x))
        for layer in self.layers:
            h = F.relu(layer(h, edge_index, edge_attr))
        return self.output_proj(h)


def _region_to_features(r: AnomalyRegion) -> list[float]:
    return [
        r.centroid_lat, r.centroid_lon, r.max_intensity,
        r.area_km2, 0.0, 0.0,
    ]


def _build_pair_graph(
    regions_t0: list[AnomalyRegion],
    regions_t1: list[AnomalyRegion],
    gate_km: float,
) -> tuple[Graph, int] | None:
    n0, n1 = len(regions_t0), len(regions_t1)
    if n0 == 0 or n1 == 0:
        return None
    all_latlon = np.array(
        [[r.centroid_lat, r.centroid_lon] for r in regions_t0]
        + [[r.centroid_lat, r.centroid_lon] for r in regions_t1]
    )
    graph = radius_graph(all_latlon, gate_km)
    return graph, n0


def _compute_association_costs(
    model: AssociationGNN,
    regions_t0: list[AnomalyRegion],
    regions_t1: list[AnomalyRegion],
    gate_km: float,
    device: torch.device,
) -> np.ndarray:
    n0, n1 = len(regions_t0), len(regions_t1)
    cost = np.full((n0, n1), _BIG)

    graph, _split = _build_pair_graph(regions_t0, regions_t1, gate_km)
    if graph is None:
        return cost

    node_feats = []
    for r in regions_t0:
        node_feats.append(_region_to_features(r))
    for r in regions_t1:
        node_feats.append(_region_to_features(r))
    x = torch.tensor(node_feats, dtype=torch.float32, device=device)
    ei = torch.tensor(graph.edge_index, dtype=torch.long, device=device)
    ea = torch.tensor(graph.edge_attr, dtype=torch.float32, device=device)

    with torch.no_grad():
        emb = model(x, ei, ea)

    emb_t0 = emb[:n0]
    emb_t1 = emb[n0:]
    scores = torch.cdist(emb_t0, emb_t1, p=2)
    scores = scores / (scores.max() + 1e-8)
    cost_arr = scores.cpu().numpy()

    for i in range(n0):
        for j in range(n1):
            dist = float(haversine_km(
                regions_t0[i].centroid_lat, regions_t0[i].centroid_lon,
                regions_t1[j].centroid_lat, regions_t1[j].centroid_lon,
            ))
            if dist <= gate_km:
                cost[i, j] = float(cost_arr[i, j])
    return cost


class GNNTracker:
    """GNN-based tracker that computes association costs via a trained GNN model."""

    def __init__(
        self,
        gnn_model: AssociationGNN | None = None,
        tracker_config: TrackerConfig | None = None,
        device: str | torch.device = "cpu",
        gate_km: float = 300.0,
        max_cost: float = 0.8,
        max_missed: int = 1,
    ) -> None:
        if not HAS_TORCH or not HAS_PYG:
            raise ImportError(
                "PyTorch and torch_geometric are required for GNNTracker. "
                "Install them with: pip install torch torch-geometric"
            )
        self.gnn_model = gnn_model or AssociationGNN()
        self.gnn_model.eval()
        self.device = torch.device(device)
        self.gnn_model.to(self.device)
        self.cfg = tracker_config or TrackerConfig()
        self.gate_km = gate_km
        self.max_cost = max_cost
        self.max_missed = max_missed
        self.tracks: list[Track] = []
        self._next_id = 1

    def _new_track(self, time_h: float, r: AnomalyRegion, parent: int | None) -> Track:
        kf = ConstantVelocityKalman(
            0.0, 0.0, self.cfg.sigma_meas_km, self.cfg.sigma_accel_kmh2, self.cfg.sigma_v0_kmh,
        )
        tr = Track(self._next_id, (r.centroid_lat, r.centroid_lon), kf, parent_id=parent)
        self._next_id += 1
        tr.points.append(self._make_point(tr, time_h, r, r.centroid_lat, r.centroid_lon, 0.0, True))
        return tr

    def _make_point(
        self, t: Track, time_h: float, r: AnomalyRegion | None,
        mlat: float | None, mlon: float | None, accel: float, observed: bool,
    ) -> TrackPoint:
        x = t.kf.x
        lat, lon = from_local_xy(x[0], x[1], *t.origin)
        speed = float(np.hypot(x[2], x[3]))
        if speed > 1e-6:
            nlat, nlon = from_local_xy(x[0] + x[2], x[1] + x[3], *t.origin)
            brg = float(bearing_deg(lat, lon, nlat, nlon))
        else:
            brg = 0.0
        return TrackPoint(
            time_h=time_h, lat=float(lat), lon=float(lon),
            meas_lat=mlat, meas_lon=mlon, speed_kmh=speed, bearing_deg=brg,
            accel_kmh2=accel, area_km2=None if r is None else r.area_km2,
            max_intensity=None if r is None else r.max_intensity,
            mean_intensity=None if r is None else r.mean_intensity,
            confidence=None if r is None else r.confidence,
            uncertainty_radius_km=t.kf.position_radius_km(), observed=observed, region=r,
        )

    def step(self, time_h: float, regions: list[AnomalyRegion]) -> dict[int, int]:
        active = [t for t in self.tracks if t.active]
        matches: dict[int, int] = {}
        if active and regions:
            cost = _compute_association_costs(
                self.gnn_model, [t.last.region for t in active if t.last.region is not None],
                regions, self.gate_km, self.device,
            )
            if cost.size > 0 and cost.shape[0] > 0 and cost.shape[1] > 0:
                rows, cols = linear_sum_assignment(cost)
                matches = {int(i): int(j) for i, j in zip(rows, cols, strict=True) if cost[i, j] <= self.max_cost}

        result: dict[int, int] = {}
        for i, t in enumerate(active):
            dt = time_h - t.last.time_h
            t.kf.predict(dt)
            region_idx = matches.get(i)
            if region_idx is not None and region_idx < len(regions):
                r = regions[region_idx]
                mx, my = to_local_xy(r.centroid_lat, r.centroid_lon, *t.origin)
                t.kf.update(float(mx), float(my))
                t.points.append(self._make_point(t, time_h, r, r.centroid_lat, r.centroid_lon, 0.0, True))
                t.missed = 0
                result[t.track_id] = region_idx
            else:
                t.missed += 1
                if t.missed > self.max_missed:
                    t.active = False
                else:
                    t.points.append(self._make_point(t, time_h, None, None, None, 0.0, False))

        used = set(matches.values())
        for j, r in enumerate(regions):
            if j in used:
                continue
            tr = self._new_track(time_h, r, None)
            self.tracks.append(tr)
            result[tr.track_id] = j
        return result

    def run(self, frames: list[tuple[float, list[AnomalyRegion]]]) -> list[Track]:
        for time_h, regions in frames:
            self.step(time_h, regions)
        return self.tracks

    def run_baseline(self, frames: list[tuple[float, list[AnomalyRegion]]]) -> list[Track]:
        from ml.tracking.tracker import RegionTracker
        fallback = RegionTracker(self.cfg)
        return fallback.run(frames)


def gnn_tracker_from_checkpoint(
    checkpoint_path: str,
    tracker_config: TrackerConfig | None = None,
    device: str | torch.device = "cpu",
    gate_km: float = 300.0,
    max_cost: float = 0.8,
) -> GNNTracker:
    if not HAS_TORCH:
        raise ImportError("PyTorch is required to load a GNN checkpoint.")
    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
    model = AssociationGNN()
    model.load_state_dict(checkpoint["model_state_dict"])
    return GNNTracker(
        gnn_model=model, tracker_config=tracker_config, device=device,
        gate_km=gate_km, max_cost=max_cost,
    )
