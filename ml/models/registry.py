"""Model registry: tracks all trained models with metadata, status lifecycle, and comparison.

Registry is stored as JSON at models/registry.json.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "models" / "registry.json"
_REPO_ROOT = _REGISTRY_PATH.parents[1]


def _portable_path(path: str | Path) -> str:
    """Repo-relative POSIX path when the file lives inside the repository (keeps registry.json machine-independent)."""
    p = Path(path)
    try:
        return p.resolve().relative_to(_REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


class ModelStatus(StrEnum):
    EXPERIMENTAL = "experimental"
    CANDIDATE = "candidate"
    RECOMMENDED = "recommended"
    BASELINE = "baseline"
    RETIRED = "retired"


_STATUS_ORDER = {
    ModelStatus.EXPERIMENTAL: 0,
    ModelStatus.CANDIDATE: 1,
    ModelStatus.RECOMMENDED: 2,
    ModelStatus.BASELINE: 3,
    ModelStatus.RETIRED: 4,
}

_PROMOTION_GATES: dict[tuple[str, str], dict[str, Any]] = {
    ("experimental", "candidate"): {"min_metrics": {"rmse": None, "mae": None}},
    ("candidate", "recommended"): {
        "min_metrics": {"extreme_recall": 0.8},
        "must_beat_baseline": True,
    },
    ("recommended", "baseline"): {
        "min_metrics": {"extreme_recall": 0.85, "precision": 0.75},
        "must_beat_baseline": True,
    },
}


def _load_registry() -> dict[str, Any]:
    if _REGISTRY_PATH.exists():
        with open(_REGISTRY_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    return {"models": {}}


def _save_registry(reg: dict[str, Any]) -> None:
    _REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_REGISTRY_PATH, "w", encoding="utf-8") as fh:
        json.dump(reg, fh, indent=2)


def _file_sha256(path: str | Path) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def register_model(
    name: str,
    version: str,
    kind: str,
    checkpoint_path: str | Path | None = None,
    training_dataset: str = "",
    training_period: tuple[str, str] | None = None,
    validation_period: tuple[str, str] | None = None,
    metrics: dict[str, float] | None = None,
    input_schema: dict[str, Any] | None = None,
    output_schema: dict[str, Any] | None = None,
    hyperparameters: dict[str, Any] | None = None,
    notes: str = "",
) -> str:
    """Register a new model version. Returns the model key (name/version)."""
    reg = _load_registry()
    key = f"{name}/{version}"

    checkpoint_sha = ""
    if checkpoint_path is not None:
        checkpoint_sha = _file_sha256(checkpoint_path)

    record = {
        "name": name,
        "version": version,
        "kind": kind,
        "status": ModelStatus.EXPERIMENTAL,
        "registered_at": datetime.now(UTC).isoformat(),
        "training_dataset": training_dataset,
        "training_period": list(training_period) if training_period else [],
        "validation_period": list(validation_period) if validation_period else [],
        "metrics": metrics or {},
        "checkpoint_path": _portable_path(checkpoint_path) if checkpoint_path else "",
        "checkpoint_sha256": checkpoint_sha,
        "input_schema": input_schema or {},
        "output_schema": output_schema or {},
        "hyperparameters": hyperparameters or {},
        "notes": notes,
        "status_history": [
            {"status": ModelStatus.EXPERIMENTAL, "at": datetime.now(UTC).isoformat()}
        ],
    }

    reg["models"][key] = record
    _save_registry(reg)
    return key


def promote_model(
    name: str,
    version: str,
    target_status: str,
    metrics: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Promote a model to a new status. Validates promotion gates.

    Returns the updated record. Raises ValueError if the promotion is not allowed.
    """
    reg = _load_registry()
    key = f"{name}/{version}"
    if key not in reg["models"]:
        raise ValueError(f"Model {key} not found in registry")

    record = reg["models"][key]
    current = ModelStatus(record["status"])
    target = ModelStatus(target_status)

    if _STATUS_ORDER[target] <= _STATUS_ORDER[current]:
        raise ValueError(f"Cannot promote from {current.value} to {target.value} (not an upgrade)")

    gate_key = (current.value, target.value)
    gate = _PROMOTION_GATES.get(gate_key, {})

    if metrics:
        record["metrics"].update(metrics)

    min_metrics = gate.get("min_metrics", {})
    for metric_name, min_val in min_metrics.items():
        if min_val is not None:
            actual = record["metrics"].get(metric_name)
            if actual is None or actual < min_val:
                raise ValueError(
                    f"Promotion to {target.value} requires {metric_name} >= {min_val}, "
                    f"got {actual}"
                )

    if gate.get("must_beat_baseline"):
        baseline_models = [
            m for m in reg["models"].values()
            if m["kind"] == record["kind"] and m["status"] == ModelStatus.BASELINE
        ]
        if baseline_models:
            best_baseline = max(baseline_models, key=lambda m: m["metrics"].get("extreme_recall", 0))
            if record["metrics"].get("extreme_recall", 0) <= best_baseline["metrics"].get("extreme_recall", 0):
                raise ValueError(
                    f"Must beat baseline extreme_recall={best_baseline['metrics'].get('extreme_recall', 0):.4f}"
                )

    record["status"] = target
    record["status_history"].append({
        "status": target.value,
        "at": datetime.now(UTC).isoformat(),
        "metrics_snapshot": dict(record["metrics"]),
    })

    if target == ModelStatus.RECOMMENDED:
        for other_key, other in reg["models"].items():
            if other_key != key and other["kind"] == record["kind"] and other["status"] == ModelStatus.RECOMMENDED:
                other["status"] = ModelStatus.CANDIDATE
                other["status_history"].append({
                    "status": ModelStatus.CANDIDATE.value,
                    "at": datetime.now(UTC).isoformat(),
                    "reason": f"Superseded by {key}",
                })

    _save_registry(reg)
    return record


def load_model_checkpoint(name: str, version: str) -> dict[str, Any] | None:
    """Load a PyTorch model checkpoint from the registered checkpoint path.

    Returns a dict with 'model_state_dict' and metadata, or None if unavailable.
    """
    record = get_model(name, version)
    if record is None:
        return None
    raw = record.get("checkpoint_path", "")
    if not raw:
        return None
    ckpt_path = Path(raw)
    if not ckpt_path.is_absolute():
        ckpt_path = _REPO_ROOT / ckpt_path
    if not ckpt_path.exists():
        return None
    try:
        import torch
        return torch.load(ckpt_path, map_location="cpu", weights_only=False)
    except ImportError:
        log.warning("PyTorch not installed; cannot load checkpoint")
        return None
    except Exception as exc:
        log.warning(f"Failed to load checkpoint {ckpt_path}: {exc}")
        return None


def get_active_model(kind: str) -> dict[str, Any] | None:
    """Get the currently recommended model for a given kind."""
    reg = _load_registry()
    for record in reg["models"].values():
        if record["kind"] == kind and record["status"] == ModelStatus.RECOMMENDED:
            return record
    for record in reg["models"].values():
        if record["kind"] == kind and record["status"] == ModelStatus.BASELINE:
            return record
    return None


def get_model(name: str, version: str) -> dict[str, Any] | None:
    """Get a specific model record."""
    reg = _load_registry()
    return reg["models"].get(f"{name}/{version}")


def list_models(kind: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
    """List all models, optionally filtered by kind and/or status."""
    reg = _load_registry()
    models = list(reg["models"].values())
    if kind:
        models = [m for m in models if m["kind"] == kind]
    if status:
        models = [m for m in models if m["status"] == status]
    return models


def compare_models(
    name_a: str, version_a: str,
    name_b: str, version_b: str,
) -> dict[str, Any]:
    """Compare two model versions side by side.

    Returns a dictionary with metrics comparison and winner per metric.
    """
    a = get_model(name_a, version_a)
    b = get_model(name_b, version_b)
    if a is None:
        raise ValueError(f"Model {name_a}/{version_a} not found")
    if b is None:
        raise ValueError(f"Model {name_b}/{version_b} not found")

    all_metrics = sorted(set(list(a["metrics"].keys()) + list(b["metrics"].keys())))
    comparison: dict[str, dict[str, Any]] = {}
    a_wins = 0
    b_wins = 0
    for metric in all_metrics:
        va = a["metrics"].get(metric)
        vb = b["metrics"].get(metric)
        if va is not None and vb is not None:
            lower_better = metric in {"rmse", "mae", "missed_events", "false_tracks", "centroid_error_km"}
            winner = (name_a if va < vb else name_b) if lower_better else (name_a if va > vb else name_b)
            if winner == name_a:
                a_wins += 1
            else:
                b_wins += 1
        else:
            winner = None
        comparison[metric] = {"model_a": va, "model_b": vb, "winner": winner}

    return {
        "model_a": f"{name_a}/{version_a}",
        "model_b": f"{name_b}/{version_b}",
        "status_a": a["status"],
        "status_b": b["status"],
        "metrics_comparison": comparison,
        "overall_winner": name_a if a_wins >= b_wins else name_b,
        "a_wins": a_wins,
        "b_wins": b_wins,
    }
