"""Model registry and evaluation records.

Only components that actually exist are registered. There are NO trained/learned models yet, so every entry is a
classical baseline with ``parameters = 0`` and ``checkpoint = None``. Planned learned models appear in
``/capabilities`` with a REQUIRES_* status, never here.
"""
from __future__ import annotations

from typing import Any

from app.services.events import iso

from ml.pipeline.real import RealResult as DemoResult

MODEL_VERSION = "baselines-v1.0"


def _metrics(result: DemoResult, method: str) -> dict[str, float]:
    row = next(r for r in result.downscaling_eval if r["method"] == method)
    return {k: row["metrics"][k]["mean"] for k in ("rmse", "peak_error", "p99_error", "psd_ratio_band", "extreme_recall")}


def list_models(result: DemoResult) -> list[dict[str, Any]]:
    created = iso(result.provenance.created_at)
    base = dict(version="0.1.0", parameters=0, checkpoint=None, training_dataset=None, training_period=None,
                created_at=created, status="BASELINE", learned=False)
    models: list[dict[str, Any]] = [
        {**base, "name": "percentile-detector", "kind": "anomaly_detector", "architecture": "piecewise-linear climatological percentile rank", "metrics": {}},
        {**base, "name": "zscore-detector", "kind": "anomaly_detector", "architecture": "(x - mean) / std", "metrics": {}},
        {**base, "name": "efi-style-detector", "kind": "anomaly_detector",
         "architecture": "EFI formula (Lalaurette 2003) on a locally built climate; not ECMWF operational EFI", "metrics": {}},
        {**base, "name": "hungarian-kalman-tracker", "kind": "tracker", "architecture": "gated cost + Hungarian assignment + constant-velocity Kalman",
         "metrics": {k: float(v) for k, v in result.tracking_eval.items() if isinstance(v, float)}},
        {**base, "name": "risk-engine", "kind": "risk", "architecture": "config-driven composite score (not calibrated, not official)", "metrics": {}},
    ]
    for r in result.downscaling_eval:
        m = r["method"]
        models.append({**base, "name": f"downscale-{m}", "kind": "downscaler",
                       "architecture": {"nearest": "nearest neighbour", "bilinear": "bilinear interpolation", "bicubic": "cubic spline",
                                        "bicubic_conservative": "cubic spline + non-negativity + coarse-cell conservation projection"}[m],
                       "metrics": _metrics(result, m),
                       "status": "BASELINE_DEFAULT" if m == "bicubic_conservative" else "BASELINE"})
    return models


def list_model_runs(result: DemoResult) -> list[dict[str, Any]]:
    common = {"dataset": result.provenance.dataset_id, "data_kind": result.provenance.data_kind.value if result.provenance else "REANALYSIS", "created_at": iso(result.provenance.created_at),
              "seed": result.scenario.config.seed, "config_hash": result.config_digest, "git_sha": result.provenance.git_sha,
              "device": "cpu", "checkpoint": None, "model_version": MODEL_VERSION}
    runs = [{"id": f"eval-downscaling-{result.config_digest}", "type": "evaluation", "target": "downscaling baselines",
             "frames": len(result.lead_hours), "metrics": {r["method"]: _metrics(result, r["method"]) for r in result.downscaling_eval}, **common},
            {"id": f"eval-tracking-{result.config_digest}", "type": "evaluation", "target": "tracking baseline", "frames": len(result.lead_hours),
             "metrics": {k: v for k, v in result.tracking_eval.items() if isinstance(v, float)}, **common}]
    return runs
