"""Events, trajectories, impact, uncertainty, explainability."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from app.core.errors import ApiError
from app.core.security import get_principal
from app.schemas.common import SEVERITY_ORDER, PageParams, envelope, page_params, paginate
from app.services import events as ev
from app.services.store import EventRecord, ProductStore
from fastapi import APIRouter, Depends, Query, Request

router = APIRouter(prefix="/events", tags=["events"], dependencies=[Depends(get_principal)])
SORTABLE = {"severity", "first_valid_time", "last_valid_time", "peak_intensity", "max_area_km2", "risk_score"}


def get_store(request: Request) -> ProductStore:
    store = request.app.state.store
    if store is None:
        raise ApiError(503, "PRODUCTS_NOT_READY", "Products not ready", "No pipeline run has completed yet.")
    return store


def get_event(request: Request, event_id: str) -> tuple[ProductStore, EventRecord]:
    store = get_store(request)
    rec = store.event(event_id)
    if rec is None:
        raise ApiError(404, "EVENT_NOT_FOUND", "Event not found", f"No event with id {event_id}.")
    return store, rec


def _parse_bbox(bbox: str | None) -> tuple[float, float, float, float] | None:
    if bbox is None:
        return None
    try:
        w, s, e, n = (float(x) for x in bbox.split(","))
    except ValueError as exc:
        raise ApiError(422, "INVALID_BBOX", "Invalid bbox", "bbox must be 'west,south,east,north' numbers") from exc
    if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
        raise ApiError(422, "INVALID_BBOX", "Invalid bbox", "Require -180<=west<east<=180 and -90<=south<north<=90")
    return w, s, e, n


def _sort_key(field: str, item: dict[str, Any]) -> Any:
    if field == "severity":
        return SEVERITY_ORDER[item["severity"]]
    if field == "peak_intensity":
        return item["peak_intensity"]["value"]
    return item[field]


@router.get("")
async def list_events(
    request: Request, p: PageParams = Depends(page_params),
    event_type: Annotated[str | None, Query(max_length=40)] = None,
    severity: Annotated[str | None, Query(description="comma separated: LOW,MODERATE,SEVERE")] = None,
    data_kind: Annotated[str | None, Query(max_length=30)] = None,
    bbox: Annotated[str | None, Query(description="west,south,east,north (WGS84)")] = None,
    from_: Annotated[datetime | None, Query(alias="from")] = None, to: datetime | None = None,
    sort: Annotated[str, Query(description="comma separated fields, '-' prefix = descending")] = "-severity,-first_valid_time",
) -> dict[str, Any]:
    store = get_store(request)
    items = [r.summary for r in store.events.values()]
    if event_type:
        items = [i for i in items if i["event_type"] == event_type.upper()]
    if severity:
        wanted = {x.strip().upper() for x in severity.split(",")}
        bad = wanted - set(SEVERITY_ORDER)
        if bad:
            raise ApiError(422, "INVALID_SEVERITY", "Invalid severity", f"Unknown severity value(s): {sorted(bad)}")
        items = [i for i in items if i["severity"] in wanted]
    if data_kind:
        items = [i for i in items if i["data_kind"] == data_kind.upper()]
    box = _parse_bbox(bbox)
    if box:
        w, s, e, n = box
        items = [i for i in items if w <= i["centroid"]["lon"] <= e and s <= i["centroid"]["lat"] <= n]
    def _naive(d: datetime) -> str:
        return d.replace(tzinfo=None).isoformat(timespec="seconds") + "Z"

    if from_:
        items = [i for i in items if i["last_valid_time"] >= _naive(from_)]
    if to:
        items = [i for i in items if i["first_valid_time"] <= _naive(to)]
    for field in reversed([f.strip() for f in sort.split(",") if f.strip()]):
        name = field.lstrip("-")
        if name not in SORTABLE:
            raise ApiError(422, "INVALID_SORT", "Invalid sort field", f"sort fields must be among {sorted(SORTABLE)}")
        items.sort(key=lambda i, n=name: _sort_key(n, i), reverse=field.startswith("-"))
    return paginate(items, p)


@router.get("/{event_id}")
async def get_event_detail(request: Request, event_id: str) -> dict[str, Any]:
    _, rec = get_event(request, event_id)
    return envelope(rec.summary)


@router.get("/{event_id}/trajectory")
async def trajectory(request: Request, event_id: str) -> dict[str, Any]:
    store, rec = get_event(request, event_id)
    return envelope(ev.trajectory_geojson(store.result, rec.track))


@router.get("/{event_id}/impact")
async def impact(request: Request, event_id: str, lead_hours: Annotated[int | None, Query(ge=0, le=500)] = None) -> dict[str, Any]:
    store, rec = get_event(request, event_id)
    return envelope(ev.impact_geojson(store.result, rec.track, lead_hours))


@router.get("/{event_id}/uncertainty")
async def uncertainty(request: Request, event_id: str) -> dict[str, Any]:
    store, rec = get_event(request, event_id)
    return envelope(ev.uncertainty_summary(store.result, rec.track))


@router.get("/{event_id}/explain")
async def explain(request: Request, event_id: str, lead_hours: Annotated[int | None, Query(ge=0, le=500)] = None) -> dict[str, Any]:
    store, rec = get_event(request, event_id)
    return envelope(ev.explain(store.result, rec.track, lead_hours))


@router.get("/{event_id}/downscaled")
async def downscaled(request: Request, event_id: str) -> dict[str, Any]:
    """Downscaling summary for the event: methods, measured metrics, physics checks. Field rasters come from /fields."""
    store, rec = get_event(request, event_id)
    r = store.result
    grid = getattr(r, "coarse_grid", None)
    if grid is None and hasattr(r, "scenario"):
        grid = getattr(r.scenario, "coarse_grid", None)

    src_res = grid.approx_resolution_km() if grid and hasattr(grid, "approx_resolution_km") else (11.1, 11.1)
    tgt_res = grid.refined(2).approx_resolution_km() if grid and hasattr(grid, "refined") else (5.5, 5.5)
    ds_eval = getattr(r, "downscaling_eval", [])
    physics = getattr(r, "physics", [])
    leads = getattr(r, "lead_hours", [0, 6, 12, 18, 24, 30, 36, 42, 48])

    return envelope({
        "event_id": event_id,
        "data_kind": r.provenance.data_kind.value if hasattr(r, "provenance") and hasattr(r.provenance, "data_kind") else "SYNTHETIC_DEMO",
        "default_method": "bicubic_conservative",
        "learned_model_available": False,
        "notice": "No learned downscaler exists yet. The downscaled product is a BASELINE interpolation of the analysis field. "
                  "Metrics compare it with the ERA5 reference.",
        "source_resolution_km": src_res,
        "target_resolution_km": tgt_res,
        "methods": [{"method": row.get("method", "bicubic_conservative") if isinstance(row, dict) else getattr(row, "method", "bicubic_conservative"),
                     "metrics": row.get("metrics", {}) if isinstance(row, dict) else getattr(row, "metrics", {})}
                    for row in ds_eval],
        "physics_checks": {str(h): p.to_dict() if hasattr(p, "to_dict") else {} for h, p in zip(leads, physics, strict=False)},
    })

