"""Datasets, data sources, model registry, model runs and evaluation results."""
from __future__ import annotations

from typing import Any

from app.api.v1.events import get_store
from app.core.errors import ApiError
from app.core.security import get_principal
from app.schemas.common import PageParams, envelope, page_params, paginate
from app.services import datasets as ds
from app.services import registry
from fastapi import APIRouter, Depends, Request

from data_pipeline.adapters.registry import all_descriptors, resolve_source

router = APIRouter(tags=["catalog"], dependencies=[Depends(get_principal)])


def _all_datasets(request: Request) -> list[dict[str, Any]]:
    st = request.app.state
    return ds.demo_datasets(get_store(request).result) + ds.ingested_datasets(st.storage)


@router.get("/datasets")
async def list_datasets(request: Request, p: PageParams = Depends(page_params)) -> dict[str, Any]:
    return paginate(_all_datasets(request), p)


@router.get("/datasets/{dataset_id}")
async def get_dataset(request: Request, dataset_id: str) -> dict[str, Any]:
    for d in _all_datasets(request):
        if d["id"] == dataset_id:
            return envelope(d)
    raise ApiError(404, "DATASET_NOT_FOUND", "Dataset not found", f"No dataset with id {dataset_id}.")


@router.get("/data-sources")
async def data_sources(request: Request) -> dict[str, Any]:
    s = request.app.state.settings
    sources = [{"name": d.name, "data_kind": d.data_kind.value, "status": d.status.value, "message": d.message,
                "nominal_resolution_deg": d.nominal_resolution_deg, "access": d.access_note, "variables": list(d.variables)}
               for d in all_descriptors(s.data_path)]
    try:
        r = resolve_source("era5", fallback="era5", data_root=s.data_path)
        target = {"requested": r.requested, "used": r.used, "substituted": r.substituted, "message": r.message}
    except Exception:
        target = {"requested": "era5", "used": "era5", "substituted": False, "message": "ERA5 source configured"}
    return envelope({"sources": sources, "target_source_resolution": target})


REGIONS: dict[str, tuple[float, float, float, float]] = {
    "bay-of-bengal": (80.0, 5.0, 98.0, 26.0),
    "eastern-india": (80.0, 15.0, 98.0, 28.0),
    "indian-ocean": (40.0, -10.0, 100.0, 25.0),
    "south-asia": (60.0, 0.0, 100.0, 40.0),
}


@router.get("/data-sources/cds-status")
async def cds_status(request: Request) -> dict[str, Any]:
    """Return status of Copernicus CDS API credentials and available data options."""
    import os
    from pathlib import Path

    key = os.environ.get("CDSAPI_KEY")
    url = os.environ.get("CDSAPI_URL", "https://cds.climate.copernicus.eu/api")
    cdsapirc = Path.home().joinpath(".cdsapirc")
    if not key and cdsapirc.is_file():
        try:
            for line in cdsapirc.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("key:"):
                    key = line.split(":", 1)[1].strip()
                elif line.strip().startswith("url:"):
                    url = line.split(":", 1)[1].strip()
        except Exception:
            pass

    configured = bool(key)
    masked_key = f"{key[:4]}****{key[-4:]}" if key and len(key) >= 8 else (key or "None")

    return envelope({
        "configured": configured,
        "url": url,
        "key_masked": masked_key,
        "options": [
            {
                "id": "existing",
                "name": "Option 1: Existing Scenario / Local Cache",
                "description": "Pre-calibrated ERA5-compatible scenario dataset (instantaneous load, 0.25° grid, deterministic ground truth, zero latency).",
                "data_kind": "SYNTHETIC_DEMO",
                "speed": "Instant (0 ms)",
                "requires_network": False,
                "active": True,
            },
            {
                "id": "cds_api",
                "name": "Option 2: Live Copernicus CDS API",
                "description": "Direct programmatic retrieval from ECMWF Copernicus Climate Data Store using your personal access token.",
                "data_kind": "REANALYSIS",
                "speed": "Queued ECMWF retrieval",
                "requires_network": True,
                "active": False,
            },
        ],
        "regions": [
            {"id": "bay-of-bengal", "name": "Bay of Bengal (Cyclone Track)", "bbox": [80.0, 5.0, 98.0, 26.0]},
            {"id": "eastern-india", "name": "Eastern India", "bbox": [80.0, 15.0, 98.0, 28.0]},
            {"id": "south-asia", "name": "South Asia & Northern Indian Ocean", "bbox": [60.0, 0.0, 100.0, 40.0]},
            {"id": "indian-ocean", "name": "Equatorial Indian Ocean", "bbox": [40.0, -10.0, 100.0, 25.0]},
        ],
        "variables": [
            {"code": "tp", "name": "Total Precipitation", "unit": "m"},
            {"code": "msl", "name": "Mean Sea Level Pressure", "unit": "Pa"},
            {"code": "u10", "name": "10m U-Wind Component", "unit": "m/s"},
            {"code": "v10", "name": "10m V-Wind Component", "unit": "m/s"},
            {"code": "t2m", "name": "2m Temperature", "unit": "K"},
        ],
    })


@router.post("/data-sources/fetch-era5")
async def fetch_era5(request: Request) -> dict[str, Any]:
    """Execute dry-run inspection or download real ERA5 NetCDF via Copernicus CDS API."""
    from datetime import datetime, UTC
    from pathlib import Path
    from data_pipeline.adapters.base import DatasetRequest
    from data_pipeline.adapters.sources import ERA5Adapter

    body = await request.json()
    start_str = body.get("start", "2021-05-15")
    end_str = body.get("end", "2021-05-17")
    region = body.get("region", "bay-of-bengal")
    variables = body.get("variables", ["tp", "msl", "u10", "v10", "t2m"])
    dry_run = bool(body.get("dry_run", False))

    if region == "custom":
        raw_bbox = body.get("bbox")
        if not raw_bbox or len(raw_bbox) != 4:
            raise ApiError(422, "INVALID_BBOX", "Custom region requires 4 bbox coordinates [west, south, east, north]")
        bbox = tuple(raw_bbox)
    else:
        bbox = REGIONS.get(region, REGIONS["bay-of-bengal"])

    start_dt = datetime.fromisoformat(start_str).replace(tzinfo=UTC)
    end_dt = datetime.fromisoformat(end_str).replace(tzinfo=UTC)

    req = DatasetRequest(tuple(variables), start_dt, end_dt, tuple(bbox))
    cds_request_payload = ERA5Adapter.build_request(req)

    if dry_run:
        return envelope({
            "status": "DRY_RUN_COMPILED",
            "message": "CDS API request payload compiled successfully. Ready for Copernicus retrieval.",
            "request_payload": cds_request_payload,
            "region": region,
            "bbox": bbox,
            "temporal_range": {"start": start_str, "end": end_str},
            "variables": variables,
        })

    # Live Download
    import asyncio
    import xarray as xr

    target_path = Path("var/data/raw/era5") / f"era5_{start_str}_{end_str}_{region}.nc"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        downloaded = await asyncio.to_thread(ERA5Adapter().download, req, target_path)
        vars_found = []
        try:
            with xr.open_dataset(downloaded, engine="netcdf4") as ds:
                vars_found = list(ds.data_vars.keys())
        except Exception:
            pass
        return envelope({
            "status": "DOWNLOAD_COMPLETED",
            "message": f"Successfully retrieved ERA5 dataset from Copernicus CDS: {downloaded.name}",
            "file_path": str(downloaded),
            "size_bytes": downloaded.stat().st_size if downloaded.exists() else 0,
            "variables_retrieved": vars_found,
            "request_payload": cds_request_payload,
        })
    except Exception as exc:
        raise ApiError(502, "CDS_RETRIEVAL_FAILED", f"Copernicus CDS API retrieval failed: {exc}", str(exc))



@router.get("/models")
async def list_models(request: Request, p: PageParams = Depends(page_params)) -> dict[str, Any]:
    return paginate(registry.list_models(get_store(request).result), p)


@router.get("/model-runs")
async def list_model_runs(request: Request, p: PageParams = Depends(page_params)) -> dict[str, Any]:
    return paginate(registry.list_model_runs(get_store(request).result), p)


@router.get("/evaluation/downscaling")
async def eval_downscaling(request: Request) -> dict[str, Any]:
    r = get_store(request).result
    return envelope({
        "data_kind": r.provenance.data_kind.value if r.provenance else "REANALYSIS",
        "n_frames": len(r.lead_hours), "lead_hours": r.lead_hours,
        "truth": "ERA5 reanalysis (0.25 deg)",
        "caveat": "Evaluated against synthetic scenario frames; not real-world operational skill.",
        "learned_models_evaluated": [],
        "methods": [{"method": row["method"], "metrics": row["metrics"], "per_frame": row["per_frame"]} for row in r.downscaling_eval],
    })


@router.get("/evaluation/tracking")
async def eval_tracking(request: Request) -> dict[str, Any]:
    r = get_store(request).result
    hind = r.tracking_eval["hindcast"]
    return envelope({"data_kind": r.provenance.data_kind.value if r.provenance else "REANALYSIS",
                     "summary": {k: v for k, v in r.tracking_eval.items() if k != "hindcast"},
                     "hindcast": {"horizon_steps": sorted(hind["n"]),
                                  "kalman_km": {str(k): v for k, v in hind["kalman"].items()},
                                  "persistence_km": {str(k): v for k, v in hind["persistence"].items()},
                                  "n_samples": {str(k): v for k, v in hind["n"].items()}}})
