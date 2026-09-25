"""Dataset catalogue: ingested datasets from real data sources."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from app.services.events import iso

from data_pipeline.storage.base import StorageProvider
from ml.pipeline.real import RealResult as DemoResult

log = logging.getLogger("app.datasets")


def demo_datasets(result: DemoResult) -> list[dict[str, Any]]:
    pid = result.provenance.dataset_id
    data_kind = result.provenance.data_kind.value if result.provenance else "REANALYSIS"
    sc = getattr(result, "scenario", None)
    init_time = getattr(sc.config, "init_time", datetime(2021, 5, 15, 0, 0)) if sc else getattr(result, "init_time", datetime(2021, 5, 15, 0, 0))
    valid_times = getattr(result, "valid_times", None)
    if valid_times is None and sc is not None:
        valid_times = getattr(sc, "valid_times", None)
    coarse_grid = getattr(result, "coarse_grid", None)
    if coarse_grid is None and sc is not None:
        coarse_grid = getattr(sc, "coarse_grid", None)
    created_at = getattr(result.provenance, "created_at", init_time)
    vt_start = iso(valid_times[0]) if valid_times else iso(init_time)
    vt_end = iso(valid_times[-1]) if valid_times else iso(init_time)
    bounds = list(coarse_grid.bounds) if coarse_grid else [-180, -90, 180, 90]
    grid_dict = coarse_grid.to_dict() if coarse_grid else {}
    grid_res = coarse_grid.approx_resolution_km() if coarse_grid else [0, 0]
    base = {"source": "SYNTHETIC", "data_kind": data_kind, "origin": "Synthetic scenario", "created_at": iso(created_at),
            "temporal_extent": {"start": vt_start, "end": vt_end, "timezone": "UTC"},
            "geographic_extent": {"west": bounds[0], "south": bounds[1], "east": bounds[2], "north": bounds[3]},
            "validation": {"ok": True, "n_findings": 0, "note": "Synthetic demo data"}}
    return [
        {**base, "id": f"{pid}:forecast", "name": "Synthetic forecast fields", "variables": {"tp": "mm/6h", "msl": "hPa", "u10": "m/s", "v10": "m/s"},
         "grid": {**grid_dict, "resolution_km": grid_res}, "n_members": int(result.member_positions.shape[0]) + 1 if hasattr(result, "member_positions") else 1},
        {**base, "id": f"{pid}:climatology", "name": "Climatology derived from synthetic data", "variables": {"tp": "mm/6h"},
         "grid": {**grid_dict, "resolution_km": grid_res}, "n_members": 1,
         "note": "Climatology built from synthetic scenario"},
    ]


def ingested_datasets(storage: StorageProvider) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for key in storage.list_keys("jobs/"):
        try:
            job = json.loads(storage.get_bytes(key))
        except Exception:  # noqa: BLE001 - a corrupt job record must not break the listing
            log.warning("skipping unreadable ingestion job record", extra={"key": key})
            continue
        if job.get("status") != "SUCCEEDED":
            continue
        findings = (job.get("validation") or {}).get("findings", [])
        out.append({
            "id": job.get("dataset_id") or job["job_id"], "name": f"Ingested {job['source']} dataset", "source": job["source"],
            "data_kind": job["data_kind"], "origin": "ingestion", "created_at": job["created_at"], "variables": job.get("units", {}),
            "dimensions": job.get("dimensions", {}), "temporal_extent": job.get("temporal_extent"), "geographic_extent": job.get("geographic_extent"),
            "checksum": job.get("checksum"), "storage_key": job.get("storage_key"), "ingestion_job_id": job["job_id"],
            "validation": {"ok": True, "n_findings": len(findings), "findings": findings},
        })
    return out
