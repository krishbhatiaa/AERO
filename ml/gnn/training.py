"""Training loop and dataset for the GNN event tracker.

Loads detection pairs from the training/ directory format and trains the association GNN
with a contrastive loss. Includes evaluation against the baseline tracker and ONNX export.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

try:
    import torch
    import torch.nn.functional as F
    from torch.utils.data import DataLoader, Dataset

    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

try:
    from torch_geometric.data import Data

    HAS_PYG = True
except ImportError:
    HAS_PYG = False

from ml.gnn.graphs import radius_graph
from ml.gnn.model import (
    _EDGE_FEATURE_DIM,
    _NODE_FEATURE_DIM,
    AssociationGNN,
    GNNTracker,
)
from ml.tracking.tracker import RegionTracker


def _load_split_json(split_path: Path) -> list[dict[str, Any]]:
    with open(split_path, encoding="utf-8") as fh:
        return json.load(fh)


def _load_detection_pair(entry: dict[str, Any]) -> tuple[list[dict], list[dict]]:
    t0_path = Path(entry["t0_detections"])
    t1_path = Path(entry["t1_detections"])
    with open(t0_path, encoding="utf-8") as fh:
        t0 = json.load(fh)
    with open(t1_path, encoding="utf-8") as fh:
        t1 = json.load(fh)
    return t0, t1


@dataclass
class DetectionPair:
    features_t0: np.ndarray
    features_t1: np.ndarray
    labels: np.ndarray
    valid_mask: np.ndarray


class TrackerDataset(Dataset):
    """Dataset of detection pairs for training the GNN association model."""

    def __init__(self, training_root: str | Path, split: str = "train", gate_km: float = 300.0) -> None:
        if not HAS_TORCH:
            raise ImportError("PyTorch is required for TrackerDataset. Install with: pip install torch")
        self.root = Path(training_root)
        self.split = split
        self.gate_km = gate_km
        split_path = self.root / "splits" / f"{split}.json"
        self.entries = _load_split_json(split_path)
        self._cache: dict[int, DetectionPair] = {}

    def __len__(self) -> int:
        return len(self.entries)

    def __getitem__(self, idx: int) -> Data:
        if idx in self._cache:
            pair = self._cache[idx]
        else:
            pair = self._load_pair(idx)
            self._cache[idx] = pair
        return self._to_graph(pair)

    def _load_pair(self, idx: int) -> DetectionPair:
        entry = self.entries[idx]
        t0_dets, t1_dets = _load_detection_pair(entry)
        n0, n1 = len(t0_dets), len(t1_dets)
        if n0 == 0 or n1 == 0:
            empty = np.zeros((max(n0, 1, n1, 1), _NODE_FEATURE_DIM), dtype=np.float32)
            return DetectionPair(empty, empty, np.zeros((1, 1), dtype=np.float32), np.zeros(1, dtype=bool))

        feats_t0 = np.array([self._det_features(d) for d in t0_dets], dtype=np.float32)
        feats_t1 = np.array([self._det_features(d) for d in t1_dets], dtype=np.float32)

        gt = entry.get("ground_truth", {})
        n_pairs = n0 * n1
        labels = np.zeros(n_pairs, dtype=np.float32)
        valid = np.ones(n_pairs, dtype=bool)
        match_list = gt.get("matches", [])
        for m in match_list:
            i, j = m["t0_idx"], m["t1_idx"]
            labels[i * n1 + j] = 1.0

        for i in range(n0):
            for j in range(n1):
                lat0, lon0 = t0_dets[i]["centroid_lat"], t0_dets[i]["centroid_lon"]
                lat1, lon1 = t1_dets[j]["centroid_lat"], t1_dets[j]["centroid_lon"]
                dist = float(np.sqrt(
                    ((lat0 - lat1) * 111.0) ** 2 + ((lon0 - lon1) * 111.0 * np.cos(np.radians(lat0))) ** 2
                ))
                if dist > self.gate_km:
                    valid[i * n1 + j] = False

        return DetectionPair(feats_t0, feats_t1, labels.reshape(n0, n1), valid.reshape(n0, n1))

    def _det_features(self, d: dict) -> list[float]:
        return [
            d.get("centroid_lat", 0.0), d.get("centroid_lon", 0.0),
            d.get("max_intensity", 0.0), d.get("area_km2", 0.0),
            d.get("speed_kmh", 0.0), d.get("bearing_deg", 0.0),
        ]

    def _to_graph(self, pair: DetectionPair) -> Data:
        n0 = pair.features_t0.shape[0]
        n1 = pair.features_t1.shape[0]
        x = np.concatenate([pair.features_t0, pair.features_t1], axis=0)
        latlon = x[:, :2]
        valid_mask = pair.valid_mask.copy()

        graph = radius_graph(latlon, self.gate_km)
        edge_index = torch.tensor(graph.edge_index, dtype=torch.long)
        edge_attr = torch.tensor(graph.edge_attr, dtype=torch.float32)
        x_tensor = torch.tensor(x, dtype=torch.float32)
        labels = torch.tensor(pair.labels, dtype=torch.float32)
        mask = torch.tensor(valid_mask, dtype=torch.bool)

        data = Data(
            x=x_tensor, edge_index=edge_index, edge_attr=edge_attr,
            y=labels, mask=mask,
        )
        data.n0 = n0
        data.n1 = n1
        return data


def _association_loss(
    model: AssociationGNN,
    batch: Any,
    margin: float = 1.0,
) -> torch.Tensor:
    x = batch.x
    emb = model(x, batch.edge_index, batch.edge_attr)
    n0 = batch.n0
    n1 = batch.n1
    emb_t0 = emb[:n0]
    emb_t1 = emb[n0 : n0 + n1]
    dist = torch.cdist(emb_t0, emb_t1, p=2)
    dist_norm = dist / (dist.max() + 1e-8)

    labels = batch.y
    mask = batch.mask
    pos_dist = dist_norm[labels > 0.5]
    neg_dist = dist_norm[(labels < 0.5) & mask]

    if pos_dist.numel() == 0:
        return torch.tensor(0.0, device=dist.device, requires_grad=True)
    if neg_dist.numel() == 0:
        return pos_dist.mean()

    pos_loss = pos_dist.mean()
    hard_neg = neg_dist.sort(descending=True).values[: min(len(neg_dist), pos_dist.numel() * 3)]
    neg_loss = F.relu(margin - hard_neg).mean()
    return pos_loss + neg_loss


@dataclass
class TrainConfig:
    epochs: int = 50
    batch_size: int = 4
    lr: float = 1e-3
    weight_decay: float = 1e-4
    gate_km: float = 300.0
    max_cost: float = 0.8
    hidden_dim: int = 32
    n_layers: int = 3
    margin: float = 1.0
    val_interval: int = 5
    checkpoint_dir: str = "models/gnn_checkpoints"
    onnx_export: bool = True
    patience: int = 10
    use_mixed_precision: bool = True
    gradient_accumulation_steps: int = 8
    gradient_checkpointing: bool = True


def train_gnn_tracker(
    training_root: str | Path,
    config: TrainConfig | None = None,
) -> dict[str, Any]:
    if not HAS_TORCH:
        raise ImportError("PyTorch is required for training. Install with: pip install torch torch-geometric")
    cfg = config or TrainConfig()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    train_ds = TrackerDataset(training_root, "train", cfg.gate_km)
    val_ds = TrackerDataset(training_root, "validation", cfg.gate_km)
    train_loader = DataLoader(train_ds, batch_size=cfg.batch_size, shuffle=True, pin_memory=True)
    val_loader = DataLoader(val_ds, batch_size=cfg.batch_size, shuffle=False)

    model = AssociationGNN(
        node_dim=_NODE_FEATURE_DIM, edge_dim=_EDGE_FEATURE_DIM,
        hidden=cfg.hidden_dim, n_layers=cfg.n_layers,
    ).to(device)
    if cfg.gradient_checkpointing and hasattr(model, "gradient_checkpointing_enable"):
        model.gradient_checkpointing_enable()
    optimizer = torch.optim.AdamW(model.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=cfg.epochs)

    scaler = torch.amp.GradScaler("cuda", enabled=cfg.use_mixed_precision and device.type == "cuda")

    ckpt_dir = Path(cfg.checkpoint_dir)
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    best_val_loss = float("inf")
    patience_counter = 0
    history: dict[str, list[float]] = {"train_loss": [], "val_loss": []}

    for epoch in range(cfg.epochs):
        model.train()
        train_losses = []
        optimizer.zero_grad()
        for step, batch in enumerate(train_loader):
            batch = batch.to(device)
            with torch.amp.autocast("cuda", enabled=cfg.use_mixed_precision and device.type == "cuda"):
                loss = _association_loss(model, batch, cfg.margin) / cfg.gradient_accumulation_steps
            scaler.scale(loss).backward()
            if (step + 1) % cfg.gradient_accumulation_steps == 0:
                scaler.step(optimizer)
                scaler.update()
                optimizer.zero_grad()
            train_losses.append(float(loss) * cfg.gradient_accumulation_steps)
        scheduler.step()
        avg_train = float(np.mean(train_losses)) if train_losses else 0.0
        history["train_loss"].append(avg_train)

        if (epoch + 1) % cfg.val_interval == 0:
            model.eval()
            val_losses = []
            with torch.no_grad():
                for batch in val_loader:
                    batch = batch.to(device)
                    with torch.amp.autocast("cuda", enabled=cfg.use_mixed_precision and device.type == "cuda"):
                        loss = _association_loss(model, batch, cfg.margin)
                    val_losses.append(float(loss))
            avg_val = float(np.mean(val_losses)) if val_losses else 0.0
            history["val_loss"].append(avg_val)

            if avg_val < best_val_loss:
                best_val_loss = avg_val
                patience_counter = 0
                ckpt = {
                    "model_state_dict": model.state_dict(),
                    "epoch": epoch,
                    "val_loss": avg_val,
                    "config": {
                        "hidden_dim": cfg.hidden_dim,
                        "n_layers": cfg.n_layers,
                        "gate_km": cfg.gate_km,
                    },
                }
                torch.save(ckpt, ckpt_dir / "best.pt")
            else:
                patience_counter += cfg.val_interval
                if patience_counter >= cfg.patience:
                    break

    model.eval()
    torch.save({
        "model_state_dict": model.state_dict(),
        "epoch": epoch,
        "config": {
            "hidden_dim": cfg.hidden_dim,
            "n_layers": cfg.n_layers,
            "gate_km": cfg.gate_km,
        },
    }, ckpt_dir / "final.pt")

    onnx_path = ckpt_dir / "model.onnx"
    if cfg.onnx_export:
        dummy_x = torch.randn(10, _NODE_FEATURE_DIM, device=device)
        dummy_ei = torch.randint(0, 10, (2, 20), device=device)
        dummy_ea = torch.randn(20, _EDGE_FEATURE_DIM, device=device)
        torch.onnx.export(
            model, (dummy_x, dummy_ei, dummy_ea), str(onnx_path),
            input_names=["x", "edge_index", "edge_attr"],
            output_names=["embedding"],
            dynamic_axes={"x": {0: "n_nodes"}, "edge_index": {1: "n_edges"}, "edge_attr": {0: "n_edges"}},
        )

    return {
        "history": history,
        "best_val_loss": best_val_loss,
        "checkpoint_dir": str(ckpt_dir),
    }


def evaluate_tracker(
    training_root: str | Path,
    gnn_model_path: str | Path,
    split: str = "test",
    gate_km: float = 300.0,
) -> dict[str, float]:
    if not HAS_TORCH:
        raise ImportError("PyTorch is required for evaluation.")
    split_path = Path(training_root) / "splits" / f"{split}.json"
    entries = _load_split_json(split_path)

    device = torch.device("cpu")
    checkpoint = torch.load(gnn_model_path, map_location=device, weights_only=False)
    cfg_dict = checkpoint.get("config", {})
    model = AssociationGNN(
        node_dim=_NODE_FEATURE_DIM, edge_dim=_EDGE_FEATURE_DIM,
        hidden=cfg_dict.get("hidden_dim", 64),
        n_layers=cfg_dict.get("n_layers", 3),
    )
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()

    gnn_tracker = GNNTracker(gnn_model=model, gate_km=gate_km, device=device)
    baseline_tracker = RegionTracker()

    gnn_centroid_errors: list[float] = []
    baseline_centroid_errors: list[float] = []
    gnn_missed = 0
    baseline_missed = 0
    gnn_false = 0
    baseline_false = 0

    for entry in entries:
        gt = entry.get("ground_truth", {})
        gt_matches = {m["t0_idx"]: m["t1_idx"] for m in gt.get("matches", [])}

        t0_dets_raw, t1_dets_raw = _load_detection_pair(entry)
        if not t0_dets_raw or not t1_dets_raw:
            continue

        from shapely.geometry import box as shapely_box

        from ml.extraction.regions import AnomalyRegion

        def _dict_to_region(d: dict) -> AnomalyRegion:
            bbox = d.get("bbox", [-1, -1, 1, 1])
            return AnomalyRegion(
                label=d.get("label", 0),
                centroid_lat=d["centroid_lat"], centroid_lon=d["centroid_lon"],
                peak_lat=d.get("peak_lat", d["centroid_lat"]),
                peak_lon=d.get("peak_lon", d["centroid_lon"]),
                area_km2=d.get("area_km2", 0.0),
                max_intensity=d.get("max_intensity", 0.0),
                mean_intensity=d.get("mean_intensity", 0.0),
                max_score=d.get("max_score", 0.0),
                mean_score=d.get("mean_score", 0.0),
                bbox=tuple(bbox),
                perimeter_km=d.get("perimeter_km", 0.0),
                compactness=d.get("compactness", 0.0),
                elongation=d.get("elongation", 1.0),
                confidence=d.get("confidence", 0.5),
                n_cells=d.get("n_cells", 1),
                footprint=shapely_box(bbox[0], bbox[1], bbox[2], bbox[3]),
                cell_mask=None,
            )

        regions_t0 = [_dict_to_region(d) for d in t0_dets_raw]
        regions_t1 = [_dict_to_region(d) for d in t1_dets_raw]

        gnn_tracker.tracks.clear()
        gnn_tracker._next_id = 1
        gnn_tracker.step(0.0, regions_t0)
        gnn_result = gnn_tracker.step(1.0, regions_t1)

        baseline_tracker.tracks.clear()
        baseline_tracker._next_id = 1
        baseline_tracker.step(0.0, regions_t0)
        baseline_result = baseline_tracker.step(1.0, regions_t1)

        for t0_idx, t1_idx in gt_matches.items():
            for tracker_result, errors_list, missed_counter in [
                (gnn_result, gnn_centroid_errors, "gnn"),
                (baseline_result, baseline_centroid_errors, "baseline"),
            ]:
                matched_t1 = None
                for tid, ridx in tracker_result.items():
                    if ridx == t1_idx:
                        matched_t1 = tid
                        break
                if matched_t1 is not None:
                    lat_err = abs(regions_t0[t0_idx].centroid_lat - regions_t1[t1_idx].centroid_lat)
                    lon_err = abs(regions_t0[t0_idx].centroid_lon - regions_t1[t1_idx].centroid_lon)
                    errors_list.append(float(np.sqrt((lat_err * 111) ** 2 + (lon_err * 111) ** 2)))
                else:
                    if missed_counter == "gnn":
                        gnn_missed += 1
                    else:
                        baseline_missed += 1

        gnn_matched_ridx = set(gnn_result.values())
        baseline_matched_ridx = set(baseline_result.values())
        gt_t1_indices = set(gt_matches.values())
        gnn_false += len(gnn_matched_ridx - gt_t1_indices)
        baseline_false += len(baseline_matched_ridx - gt_t1_indices)

    def _safe_mean(vals: list[float]) -> float:
        return float(np.mean(vals)) if vals else float("nan")

    return {
        "gnn_centroid_error_km": _safe_mean(gnn_centroid_errors),
        "baseline_centroid_error_km": _safe_mean(baseline_centroid_errors),
        "gnn_missed_events": gnn_missed,
        "baseline_missed_events": baseline_missed,
        "gnn_false_tracks": gnn_false,
        "baseline_false_tracks": baseline_false,
    }
