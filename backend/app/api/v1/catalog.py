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
