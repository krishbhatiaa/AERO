"""Training dataset builder: processes raw Zarr data into the training/ directory format.

Directory layout::

    training/
        input/      # Coarse resolution inputs
        target/     # Fine resolution targets
        metadata/   # JSON files with provenance, grid specs, time info
        splits/
            train.json
            validation.json
            test.json

Supports time-based splits to prevent temporal leakage between adjacent weather frames.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _grid_to_dict(grid: Any) -> dict[str, float | int]:
    if hasattr(grid, "to_dict"):
        return grid.to_dict()
    return {
        "lat_min": float(grid.lat_min), "lon_min": float(grid.lon_min),
        "dlat": float(grid.dlat), "dlon": float(grid.dlon),
        "nlat": int(grid.nlat), "nlon": int(grid.nlon),
    }


def time_based_split(
    indices: list[int],
    train_ratio: float = 0.7,
    val_ratio: float = 0.15,
    min_gap: int = 2,
) -> dict[str, list[int]]:
    """Split indices assuming chronological order with gap to prevent leakage.

    Args:
        indices: Sorted time-step indices.
        train_ratio: Fraction of data for training.
        val_ratio: Fraction for validation (rest is test).
        min_gap: Minimum number of time steps between train and val/test boundaries.
    """
    n = len(indices)
    train_end = int(n * train_ratio)
    val_end = int(n * (train_ratio + val_ratio))
    train_end = max(0, train_end - min_gap)
    val_end = min(n, val_end + min_gap)
    return {
        "train": indices[:train_end],
        "validation": indices[train_end:val_end],
        "test": indices[val_end:],
    }


def build_training_dataset(
    input_arrays: list[np.ndarray],
    target_arrays: list[np.ndarray],
    output_dir: str | Path,
    coarse_grid: Any | None = None,
    fine_grid: Any | None = None,
    source: str = "unknown",
    variables: list[str] | None = None,
    train_ratio: float = 0.7,
    val_ratio: float = 0.15,
    min_gap: int = 2,
    task: str = "downscaling",
) -> dict[str, Any]:
    """Build the training dataset directory from arrays.

    Args:
        input_arrays: List of coarse-resolution input arrays.
        target_arrays: List of fine-resolution target arrays.
        output_dir: Root output directory (will create input/, target/, metadata/, splits/).
        coarse_grid: GridSpec for the coarse grid.
        fine_grid: GridSpec for the fine grid.
        source: Data source identifier.
        variables: List of variable names.
        train_ratio: Fraction for training split.
        val_ratio: Fraction for validation split.
        min_gap: Minimum gap between splits.
        task: Either "downscaling" or "tracking".

    Returns:
        Dictionary with build metadata.
    """
    output_path = Path(output_dir)
    input_dir = output_path / "input"
    target_dir = output_path / "target"
    metadata_dir = output_path / "metadata"
    splits_dir = output_path / "splits"
    for d in (input_dir, target_dir, metadata_dir, splits_dir):
        d.mkdir(parents=True, exist_ok=True)

    if len(input_arrays) != len(target_arrays):
        raise ValueError(f"input/target length mismatch: {len(input_arrays)} vs {len(target_arrays)}")

    n = len(input_arrays)
    input_paths: list[str] = []
    target_paths: list[str] = []

    for i, (inp, tgt) in enumerate(zip(input_arrays, target_arrays, strict=True)):
        inp_path = input_dir / f"{i:06d}.npy"
        tgt_path = target_dir / f"{i:06d}.npy"
        np.save(inp_path, inp)
        np.save(tgt_path, tgt)
        input_paths.append(str(inp_path))
        target_paths.append(str(tgt_path))

    splits = time_based_split(list(range(n)), train_ratio, val_ratio, min_gap)
    for split_name, indices in splits.items():
        split_entries = []
        for idx in indices:
            entry: dict[str, Any] = {
                "input_path": input_paths[idx],
                "target_path": target_paths[idx],
                "index": idx,
            }
            if coarse_grid is not None:
                entry["coarse_grid"] = _grid_to_dict(coarse_grid)
            if fine_grid is not None:
                entry["fine_grid"] = _grid_to_dict(fine_grid)
            split_entries.append(entry)
        with open(splits_dir / f"{split_name}.json", "w", encoding="utf-8") as fh:
            json.dump(split_entries, fh, indent=2)

    metadata = {
        "source": source,
        "variables": variables or [],
        "n_samples": n,
        "task": task,
        "created_at": datetime.utcnow().isoformat(),
        "splits": {k: len(v) for k, v in splits.items()},
        "input_checksums": [_file_sha256(Path(p)) for p in input_paths[:5]],
        "target_checksums": [_file_sha256(Path(p)) for p in target_paths[:5]],
    }
    if coarse_grid is not None:
        metadata["coarse_grid"] = _grid_to_dict(coarse_grid)
    if fine_grid is not None:
        metadata["fine_grid"] = _grid_to_dict(fine_grid)

    with open(metadata_dir / "dataset.json", "w", encoding="utf-8") as fh:
        json.dump(metadata, fh, indent=2)

    return {
        "output_dir": str(output_path),
        "n_samples": n,
        "splits": {k: len(v) for k, v in splits.items()},
        "metadata": metadata,
    }


def load_split(
    training_root: str | Path,
    split: str = "train",
) -> list[dict[str, Any]]:
    """Load a split file and return the list of entries."""
    split_path = Path(training_root) / "splits" / f"{split}.json"
    if not split_path.exists():
        raise FileNotFoundError(f"Split file not found: {split_path}")
    with open(split_path, encoding="utf-8") as fh:
        return json.load(fh)


def load_metadata(training_root: str | Path) -> dict[str, Any]:
    """Load the dataset metadata."""
    meta_path = Path(training_root) / "metadata" / "dataset.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"Metadata not found: {meta_path}")
    with open(meta_path, encoding="utf-8") as fh:
        return json.load(fh)


def build_tracking_dataset(
    detection_frames: list[list[dict[str, Any]]],
    output_dir: str | Path,
    source: str = "unknown",
    train_ratio: float = 0.7,
    val_ratio: float = 0.15,
    min_gap: int = 2,
) -> dict[str, Any]:
    """Build a tracking training dataset with detection pairs.

    Args:
        detection_frames: List of frames, each containing detection dictionaries.
        output_dir: Root output directory.
        source: Data source identifier.
        train_ratio: Fraction for training.
        val_ratio: Fraction for validation.
        min_gap: Minimum gap between splits.

    Returns:
        Build metadata.
    """
    output_path = Path(output_dir)
    target_dir = output_path / "target"
    metadata_dir = output_path / "metadata"
    splits_dir = output_path / "splits"
    for d in (target_dir, metadata_dir, splits_dir):
        d.mkdir(parents=True, exist_ok=True)

    detection_dir = output_path / "detections"
    detection_dir.mkdir(parents=True, exist_ok=True)
    det_paths: list[str] = []
    for i, frame in enumerate(detection_frames):
        det_path = detection_dir / f"frame_{i:06d}.json"
        with open(det_path, "w", encoding="utf-8") as fh:
            json.dump(frame, fh, indent=2)
        det_paths.append(str(det_path))

    pairs: list[dict[str, Any]] = []
    for i in range(len(detection_frames) - 1):
        pairs.append({
            "t0_detections": det_paths[i],
            "t1_detections": det_paths[i + 1],
            "t0_frame": i,
            "t1_frame": i + 1,
            "ground_truth": {"matches": []},
        })

    n = len(pairs)
    splits = time_based_split(list(range(n)), train_ratio, val_ratio, min_gap)
    for split_name, indices in splits.items():
        split_entries = [pairs[i] for i in indices]
        with open(splits_dir / f"{split_name}.json", "w", encoding="utf-8") as fh:
            json.dump(split_entries, fh, indent=2)

    metadata = {
        "source": source,
        "task": "tracking",
        "n_pairs": n,
        "n_frames": len(detection_frames),
        "created_at": datetime.utcnow().isoformat(),
        "splits": {k: len(v) for k, v in splits.items()},
    }
    with open(metadata_dir / "dataset.json", "w", encoding="utf-8") as fh:
        json.dump(metadata, fh, indent=2)

    return {
        "output_dir": str(output_path),
        "n_pairs": n,
        "splits": {k: len(v) for k, v in splits.items()},
        "metadata": metadata,
    }
