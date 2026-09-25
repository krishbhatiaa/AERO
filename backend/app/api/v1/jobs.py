"""Jobs and predictions. Long-running work is asynchronous: POST returns 202 with a job to poll or follow via WebSocket."""
from __future__ import annotations

import re
from typing import Any

from app.core.errors import ApiError
from app.core.logging import request_id_var
from app.core.security import Principal, get_principal, require_role
from app.schemas.common import JobCreate, PageParams, PredictionCreate, envelope, page_params, paginate
from app.services.jobs import Job, JobFailure
from app.services.store import ProductStore
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from data_pipeline.adapters.base import DatasetRequest
from data_pipeline.adapters.sources import ADAPTERS
from data_pipeline.ingestion.pipeline import run_ingestion
from data_pipeline.validation.checks import ValidationSchema
from ml.pipeline.real import run_real_pipeline

router = APIRouter(tags=["jobs"])
_DATASET_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _pipeline_runner(app_state: Any):  # noqa: ANN202
    def runner(job: Job, progress):  # noqa: ANN001, ANN202
        result = run_real_pipeline(progress=progress)
        store = ProductStore(result)
        app_state.store = store
        for e in store.events.values():
            app_state.ws.broadcast_threadsafe("events", "event.updated", {"event_id": e.id, "severity": e.summary["severity"], "data_kind": "REANALYSIS"})
        for a in store.alerts.values():
            app_state.ws.broadcast_threadsafe("alerts", "alert.created", {"alert_id": a["id"], "severity": a["severity"], "data_kind": "REANALYSIS"})
        return {"event_ids": list(store.events), "alert_ids": list(store.alerts), "data_kind": "REANALYSIS",
                "pipeline_config_hash": result.config_digest}

    return runner


def _ingest_runner(app_state: Any, source: str, dataset_id: str):  # noqa: ANN202
    def runner(job: Job, progress):  # noqa: ANN001, ANN202
        progress("ingest_start", 0.05)
        if source not in ADAPTERS:
            raise ApiError(422, "UNKNOWN_SOURCE", "Unknown data source", f"source must be one of {sorted(ADAPTERS)}")
        adapter = ADAPTERS[source](app_state.settings.data_path)
        vm = adapter.variable_map()
        schema = ValidationSchema(required_vars=tuple(vm), expected_units={k: v["from_units"] for k, v in vm.items() if "from_units" in v})
        req = DatasetRequest()
        ing = run_ingestion(adapter, req, app_state.storage, schema, dataset_id, job_id=job.id)
        progress("ingest_done", 1.0)
        summary = {"ingestion_status": str(ing.status), "storage_key": ing.storage_key, "dataset_id": dataset_id,
                   "validation_ok": bool((ing.validation or {}).get("ok", False)), "error": ing.error}
        if ing.status != "SUCCEEDED":
            raise JobFailure(ing.error or "ingestion failed")
        return summary

    return runner


def _submit(request: Request, principal: Principal, type_: str, params: dict[str, Any], runner: Any) -> JSONResponse:
    st = request.app.state
    job = st.jobs.submit(type_, params, runner, principal.name, request_id_var.get())
    st.audit.record("job.created", principal.name, job_id=job.id, type=type_, params=params)
    body = envelope(job.to_dict())
    return JSONResponse(body, status_code=202, headers={"Location": f"/api/v1/jobs/{job.id}"})


@router.post("/predictions", status_code=202)
async def create_prediction(request: Request, body: PredictionCreate, principal: Principal = Depends(require_role("analyst"))) -> JSONResponse:
    """Run detection -> tracking -> downscaling -> risk -> alert on real data (asynchronous)."""
    runner = _pipeline_runner(request.app.state)
    return _submit(request, principal, "prediction", body.model_dump(), runner)


@router.post("/jobs", status_code=202)
async def create_job(request: Request, body: JobCreate, principal: Principal = Depends(require_role("analyst"))) -> JSONResponse:
    st = request.app.state
    if body.type in ("prediction", "pipeline"):
        return _submit(request, principal, body.type, body.params, _pipeline_runner(st))
    source = str(body.params.get("source", "era5")).lower()
    dataset_id = str(body.params.get("dataset_id", f"{source}-ingest"))
    if source not in ADAPTERS:
        raise ApiError(422, "UNKNOWN_SOURCE", "Unknown data source", f"source must be one of {sorted(ADAPTERS)}")
    if not _DATASET_ID.match(dataset_id):
        raise ApiError(422, "INVALID_DATASET_ID", "Invalid dataset_id", "Use 1-64 characters: letters, digits, '.', '_' or '-'.")
    return _submit(request, principal, "ingest", {"source": source, "dataset_id": dataset_id}, _ingest_runner(st, source, dataset_id))


@router.get("/jobs", dependencies=[Depends(get_principal)])
async def list_jobs(request: Request, p: PageParams = Depends(page_params)) -> dict[str, Any]:
    return paginate([j.to_dict() for j in request.app.state.jobs.list()], p)


@router.get("/jobs/{job_id}", dependencies=[Depends(get_principal)])
async def get_job(request: Request, job_id: str) -> dict[str, Any]:
    job = request.app.state.jobs.get(job_id)
    if job is None:
        raise ApiError(404, "JOB_NOT_FOUND", "Job not found", f"No job with id {job_id}.")
    return envelope(job.to_dict())
