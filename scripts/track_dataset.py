"""DVC Dataset Versioning and SHA-256 tracking manager.

Generates .dvc tracking records, integrity hashes, and dataset version manifests.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "var" / "data"
DVC_DIR = ROOT_DIR / ".dvc"


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def track_dataset(dataset_path: str | Path, dataset_name: str, version: str = "v1.0.0") -> dict[str, Any]:
    """Create .dvc dataset record and manifest for dataset_path."""
    p = Path(dataset_path)
    if not p.exists():
        raise FileNotFoundError(f"Dataset path {p} does not exist.")

    sha256 = compute_sha256(p)
    file_size = p.stat().st_size

    dvc_record = {
        "outs": [
            {
                "md5": sha256[:32],
                "sha256": sha256,
                "size": file_size,
                "nfiles": 1,
                "path": p.name,
            }
        ],
        "meta": {
            "name": dataset_name,
            "version": version,
            "tracked_at": datetime.now(UTC).isoformat(),
        },
    }

    dvc_file = p.with_suffix(p.suffix + ".dvc")
    with open(dvc_file, "w", encoding="utf-8") as fh:
        json.dump(dvc_record, fh, indent=2)

    log.info(f"Generated DVC tracking record: {dvc_file} (SHA256: {sha256[:12]}...)")
    return dvc_record


def create_dvc_pipeline_config() -> Path:
    """Create dvc.yaml pipeline configuration."""
    dvc_yaml_path = ROOT_DIR / "dvc.yaml"
    pipeline_content = """# DVC Pipeline configuration for Extreme Weather AI
stages:
  ingest_era5:
    cmd: python scripts/generate_sample_era5.py
    deps:
      - scripts/generate_sample_era5.py
    outs:
      - var/data/raw/era5/era5_sample_event.nc:
          cache: true

  train_models:
    cmd: python scripts/train_all_models.py
    deps:
      - scripts/train_all_models.py
      - var/data/raw/era5/era5_sample_event.nc
    outs:
      - models/checkpoints:
          cache: true
      - models/registry.json:
          cache: false
"""
    with open(dvc_yaml_path, "w", encoding="utf-8") as fh:
        fh.write(pipeline_content)

    log.info(f"Created dvc.yaml pipeline configuration at {dvc_yaml_path}")
    return dvc_yaml_path


if __name__ == "__main__":
    create_dvc_pipeline_config()
    era5_file = DATA_DIR / "raw" / "era5" / "era5_sample_event.nc"
    if era5_file.exists():
        track_dataset(era5_file, "era5_sample_reanalysis", "v1.0.0")
