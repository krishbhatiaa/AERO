"""MLflow Experiment Tracker module.

Handles experiment tracking, metric logging, hyperparameter logging, and model artifact tracking.
Uses MLFLOW_TRACKING_TOKEN (API key) when remote MLflow server is configured, or local var/mlruns.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

API_KEY_TOKEN = "8213bb79-aa4d-4ce4-a5f9-74efd87b6e45"


class MLflowTracker:
    """Experiment tracker wrapping MLflow with fallback local JSON logging."""

    def __init__(self, experiment_name: str = "extreme-weather-ai") -> None:
        self.experiment_name = experiment_name
        self.token = os.environ.get("MLFLOW_TRACKING_TOKEN", API_KEY_TOKEN)
        self.tracking_uri = os.environ.get("MLFLOW_TRACKING_URI", "./var/mlruns")
        self.has_mlflow = False

        try:
            import mlflow
            mlflow.set_tracking_uri(self.tracking_uri)
            mlflow.set_experiment(self.experiment_name)
            self.has_mlflow = True
            log.info(f"Initialized MLflow tracker at {self.tracking_uri}")
        except Exception:
            log.info("MLflow package not installed; using local experiment run tracker.")
            self.runs_dir = Path(self.tracking_uri) / self.experiment_name
            self.runs_dir.mkdir(parents=True, exist_ok=True)

    def log_run(
        self,
        run_name: str,
        params: dict[str, Any],
        metrics: dict[str, float],
        artifacts: list[str | Path] | None = None,
        notes: str = "",
    ) -> str:
        """Log a complete experiment run with parameters, metrics, and artifacts."""
        run_id = f"run-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"

        if self.has_mlflow:
            try:
                import mlflow
                with mlflow.start_run(run_name=run_name) as run:
                    mlflow.log_params(params)
                    mlflow.log_metrics(metrics)
                    mlflow.set_tag("api_key", self.token[:8] + "...")
                    if notes:
                        mlflow.set_tag("notes", notes)
                    if artifacts:
                        for art in artifacts:
                            if Path(art).exists():
                                mlflow.log_artifact(str(art))
                    return run.info.run_id
            except Exception as exc:
                log.warning(f"MLflow remote logging exception: {exc}; logging locally.")

        # Local experiment run record fallback
        record = {
            "run_id": run_id,
            "run_name": run_name,
            "experiment_name": self.experiment_name,
            "token_sha256": self.token[:8] + "...",
            "timestamp": datetime.now(UTC).isoformat(),
            "params": params,
            "metrics": metrics,
            "artifacts": [str(a) for a in (artifacts or [])],
            "notes": notes,
        }

        out_path = Path(self.tracking_uri) / self.experiment_name / f"{run_id}.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=2)

        log.info(f"Logged experiment run {run_name} ({run_id}) to {out_path}")
        return run_id


tracker = MLflowTracker()
