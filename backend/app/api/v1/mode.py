"""Mode configuration endpoint."""
from __future__ import annotations

from typing import Any

from app.schemas.common import envelope
from fastapi import APIRouter, Request

from data_pipeline.adapters.registry import all_descriptors

router = APIRouter()


@router.get("/mode", tags=["system"])
async def get_mode(request: Request) -> dict[str, Any]:
    """Return current data mode configuration."""
    s = request.app.state.settings
    descriptors = all_descriptors(data_root=s.data_path)
    return envelope({
        "demo_mode": s.demo_mode,
        "real_data_mode": s.real_data_mode,
        "data_mode": s.data_mode,
        "model_backend": s.model_backend,
        "env": s.env,
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
