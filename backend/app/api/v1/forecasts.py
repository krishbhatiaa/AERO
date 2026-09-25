"""Forecast runs and gridded field rasters for map layers."""
from __future__ import annotations

from typing import Annotated, Any

from app.api.v1.events import get_store
from app.core.errors import ApiError
from app.core.security import get_principal
from app.schemas.common import PageParams, envelope, page_params, paginate
from app.services import events as ev
from fastapi import APIRouter, Depends, Query, Request

router = APIRouter(tags=["forecasts"], dependencies=[Depends(get_principal)])


@router.get("/forecasts")
async def list_forecasts(request: Request, p: PageParams = Depends(page_params)) -> dict[str, Any]:
    return paginate([ev.forecast_run(get_store(request).result)], p)


@router.get("/forecasts/{run_id}")
async def get_forecast(request: Request, run_id: str) -> dict[str, Any]:
    run = ev.forecast_run(get_store(request).result)
    if run["id"] != run_id:
        raise ApiError(404, "FORECAST_NOT_FOUND", "Forecast run not found", f"No forecast run with id {run_id}.")
    return envelope(run)


@router.get("/fields")
async def get_field(
    request: Request,
    product: Annotated[str, Query(pattern="^(forecast|truth|downscaled|anomaly)$")] = "forecast",
    variable: Annotated[str, Query(pattern="^(tp|msl|u10|v10|anomaly)$")] = "tp",
    lead_hours: Annotated[int, Query(ge=0, le=500)] = 0,
    method: Annotated[str | None, Query(max_length=40)] = None,
) -> dict[str, Any]:
    """Georeferenced raster (float32, base64, south-to-north rows). Cached; always labelled with its data kind."""
    store = get_store(request)
    key = f"field:{store.result.config_digest}:{store.built_at.timestamp()}:{product}:{variable}:{lead_hours}:{method}"
    payload = request.app.state.cache.get_or_set(key, 600, lambda: ev.field_payload(store.result, product, variable, lead_hours, method))
    return envelope(payload)
