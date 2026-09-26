"""Mode configuration endpoint — supports runtime switching between Simulation 1 (demo) and Simulation 2 (real ERA5)."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.api.v1.events import get_store
from app.schemas.common import envelope
from fastapi import APIRouter, Request

from data_pipeline.adapters.registry import all_descriptors

log = logging.getLogger("app")
router = APIRouter()


@router.get("/mode", tags=["system"])
async def get_mode(request: Request) -> dict[str, Any]:
    """Return current data mode configuration."""
    s = request.app.state.settings
    descriptors = all_descriptors(data_root=s.data_path)
    store = getattr(request.app.state, "store", None)
    data_kind = None
    if store is not None:
        result = getattr(store, "result", None)
        if result is not None:
            prov = getattr(result, "provenance", None)
            if prov is not None:
                dk = getattr(prov, "data_kind", None)
                data_kind = dk.value if dk else None
    return envelope({
        "demo_mode": s.demo_mode,
        "real_data_mode": s.real_data_mode,
        "data_mode": s.data_mode,
        "simulation": "1" if s.demo_mode or (not s.real_data_mode) else "2",
        "simulation_label": "Simulation 1 – Synthetic Demo" if (s.demo_mode or not s.real_data_mode) else "Simulation 2 – ERA5 Reanalysis",
        "model_backend": s.model_backend,
        "env": s.env,
        "data_kind_active": data_kind,
        "available_sources": [
            {
                "name": d.name,
                "data_kind": d.data_kind.value if d.data_kind else None,
                "status": d.status.value,
                "message": d.message,
                "variables": list(d.variables) if d.variables else [],
            }
            for d in descriptors
        ],
    })


@router.post("/mode/switch", tags=["system"])
async def switch_mode(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    """Switch between Simulation 1 (synthetic demo) and Simulation 2 (ERA5 real data)."""
    simulation = str(body.get("simulation", "1"))
    if simulation not in ("1", "2"):
        from app.core.errors import ApiError
        raise ApiError(422, "INVALID_SIM", "Invalid simulation", "simulation must be '1' or '2'")

    app = request.app
    s = app.state.settings

    if simulation == "1":
        # Switch to demo mode
        log.info("Switching to Simulation 1 (synthetic demo)")
        try:
            from ml.pipeline.demo import run_demo_pipeline
            result = await asyncio.to_thread(run_demo_pipeline)
            from app.services.store import ProductStore
            app.state.store = ProductStore(result)
            return envelope({
                "simulation": "1",
                "simulation_label": "Simulation 1 – Synthetic Demo",
                "data_mode": "demo",
                "message": "Switched to Simulation 1 (Synthetic Demo). Full cyclone track with rich raster fields.",
            })
        except Exception as exc:
            log.error("Failed to switch to demo pipeline", exc_info=True)
            from app.core.errors import ApiError
            raise ApiError(500, "SWITCH_FAILED", "Mode switch failed", str(exc)) from exc
    else:
        # Switch to real ERA5 mode
        log.info("Switching to Simulation 2 (ERA5 reanalysis)")
        try:
            from ml.pipeline.real import run_real_pipeline
            result = await asyncio.to_thread(run_real_pipeline)
            from app.services.store import ProductStore
            app.state.store = ProductStore(result)
            return envelope({
                "simulation": "2",
                "simulation_label": "Simulation 2 – ERA5 Reanalysis",
                "data_mode": "real",
                "message": "Switched to Simulation 2 (ERA5 Reanalysis). Real observed data from May 2021.",
            })
        except Exception as exc:
            log.error("Failed to switch to real pipeline", exc_info=True)
            from app.core.errors import ApiError
            raise ApiError(500, "SWITCH_FAILED", "Mode switch failed", str(exc)) from exc
