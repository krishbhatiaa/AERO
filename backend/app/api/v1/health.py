"""Health, liveness, readiness and capability endpoints."""
from __future__ import annotations

import time
from typing import Any

from app.core.config import APP_VERSION
from app.core.errors import problem
from app.core.security import get_principal
from app.schemas.common import envelope
from app.services.capabilities import capabilities_payload
from app.services.health import check_dependencies
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from data_pipeline.adapters.registry import resolve_source

router = APIRouter()


def _mode(request: Request) -> dict[str, Any]:
    s = request.app.state.settings
    mode: dict[str, Any] = {"demo_mode": s.demo_mode, "real_data_mode": s.real_data_mode, "env": s.env,
                            "auth_mode": s.auth_mode}
    if s.real_data_mode:
        try:
            r = resolve_source("era5", fallback="era5", data_root=s.data_path)
            mode["source_resolution"] = {"requested": r.requested, "used": r.used, "substituted": r.substituted, "message": r.message}
            mode["data_kind_in_use"] = "REANALYSIS"
        except Exception:
            mode["data_kind_in_use"] = "REANALYSIS"
            mode["note"] = "REAL_DATA_MODE is active but ERA5 data may not be downloaded yet."
    else:
        mode["data_kind_in_use"] = "REANALYSIS"
    return mode


@router.get("/live", tags=["health"])
async def live() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/health", tags=["health"])
async def health(request: Request) -> dict[str, Any]:
    st = request.app.state
    return envelope({"status": "ok", "version": APP_VERSION, "uptime_s": round(time.time() - st.started_at, 1), "mode": _mode(request),
                     "git_sha": st.settings.git_sha})


@router.get("/ready", tags=["health"])
async def ready(request: Request) -> JSONResponse:
    st = request.app.state
    report = check_dependencies(st.settings, st.storage, st.store is not None, st.ws.count, st.cache.name)
    if report["ready"]:
        return JSONResponse(envelope(report))
    resp = problem(503, "NOT_READY", "Service not ready", "One or more required dependencies are unavailable.", extra={"report": report})
    return resp


@router.get("/capabilities", tags=["health"], dependencies=[Depends(get_principal)])
async def capabilities(request: Request) -> dict[str, Any]:
    return envelope(capabilities_payload(_mode(request)))
