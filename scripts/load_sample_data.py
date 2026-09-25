"""Run the ingestion pipeline on the built-in synthetic sample and store the validated Zarr + job record.

    python scripts/load_sample_data.py [--data-path ./var/data] [--dataset-id synthetic-sample]

Demonstrates the full ingestion chain (checksum -> metadata -> validation -> canonicalisation -> chunking -> Zarr -> job
record) without any external data. Real sources (ERA5 etc.) use the same code path via their adapters.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data_pipeline.adapters.base import DatasetRequest  # noqa: E402
from data_pipeline.adapters.sources import SyntheticAdapter  # noqa: E402
from data_pipeline.ingestion.pipeline import run_ingestion  # noqa: E402
from data_pipeline.storage.local import LocalStorageProvider  # noqa: E402
from data_pipeline.validation.checks import ValidationSchema  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-path", default="./var/data")
    ap.add_argument("--dataset-id", default="synthetic-sample")
    a = ap.parse_args()
    store = LocalStorageProvider(a.data_path)
    schema = ValidationSchema(required_vars=("tp", "msl", "u10", "v10"), expected_units={"tp": "mm", "msl": "Pa", "u10": "m s-1", "v10": "m s-1"},
                              valid_ranges={"tp": (0.0, 2000.0), "msl": (80000.0, 110000.0)})
    job = run_ingestion(SyntheticAdapter(), DatasetRequest(("tp", "msl", "u10", "v10")), store, schema, a.dataset_id)
    print(json.dumps({"job_id": job.job_id, "status": str(job.status), "data_kind": job.data_kind, "storage_key": job.storage_key,
                      "dimensions": job.dimensions, "checksum": job.checksum, "error": job.error,
                      "steps": {s.name: s.status for s in job.steps}}, indent=2))
    return 0 if str(job.status) == "SUCCEEDED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
