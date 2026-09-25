"""Shared request/response schemas and pagination helpers."""
from __future__ import annotations

from typing import Annotated, Any, Literal

from app.core.logging import request_id_var
from fastapi import Query
from pydantic import BaseModel, Field

SEVERITY_ORDER = {"LOW": 0, "MODERATE": 1, "SEVERE": 2}


class PageParams(BaseModel):
    page: int = 1
    page_size: int = 50


def page_params(
    page: Annotated[int, Query(ge=1, description="1-based page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=200, description="items per page (max 200)")] = 50,
) -> PageParams:
    return PageParams(page=page, page_size=page_size)


def envelope(data: Any, **meta: Any) -> dict[str, Any]:
    """Standard ``{data, meta}`` response body; ``meta.request_id`` always present."""
    return {"data": data, "meta": {"request_id": request_id_var.get(), **meta}}


def paginate(items: list[Any], p: PageParams) -> dict[str, Any]:
    start = (p.page - 1) * p.page_size
    return envelope(items[start : start + p.page_size], page=p.page, page_size=p.page_size, total=len(items))


class PredictionCreate(BaseModel):
    """Run the full pipeline on real ERA5 data. Bounds are enforced to protect the server."""

    scenario_seed: int = Field(default=7, ge=0, le=1_000_000)
    n_members: int = Field(default=10, ge=2, le=30)


class JobCreate(BaseModel):
    type: Literal["prediction", "ingest", "pipeline"]
    params: dict[str, Any] = Field(default_factory=dict)
