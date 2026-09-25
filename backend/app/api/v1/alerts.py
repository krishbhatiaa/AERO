"""Alerts API (CAP-IN XML export & Dissemination)."""
from __future__ import annotations

from typing import Annotated, Any

from app.api.v1.events import get_store
from app.core.errors import ApiError
from app.core.security import get_principal, require_role
from app.schemas.common import SEVERITY_ORDER, PageParams, envelope, page_params, paginate
from app.services.alerts import alert_geojson
from app.services.dissemination import dissemination_service
from fastapi import APIRouter, Body, Depends, Query, Request, Response
from fastapi.responses import JSONResponse

from ml.risk.cap_xml import export_cap_xml, export_cap_xml_feed

router = APIRouter(prefix="/alerts", tags=["alerts"], dependencies=[Depends(get_principal)])


@router.get("")
async def list_alerts(
    request: Request, p: PageParams = Depends(page_params),
    severity: Annotated[str | None, Query(description="comma separated: LOW,MODERATE,SEVERE")] = None,
    event_id: Annotated[str | None, Query(max_length=64)] = None,
    sort: Annotated[str, Query(pattern="^-?(created_at|severity)$")] = "-severity",
) -> dict[str, Any]:
    items = list(get_store(request).alerts.values())
    if severity:
        wanted = {x.strip().upper() for x in severity.split(",")}
        if wanted - set(SEVERITY_ORDER):
            raise ApiError(422, "INVALID_SEVERITY", "Invalid severity", "severity must be LOW, MODERATE or SEVERE")
        items = [a for a in items if a["severity"] in wanted]
    if event_id:
        items = [a for a in items if a["event_id"] == event_id]
    name = sort.lstrip("-")
    items.sort(key=lambda a: SEVERITY_ORDER[a["severity"]] if name == "severity" else a[name], reverse=sort.startswith("-"))
    return paginate(items, p)


@router.get("/xml")
async def export_all_alerts_xml(request: Request) -> Response:
    """Export active alerts as a CAP-IN v1.2 XML feed."""
    items = list(get_store(request).alerts.values())
    xml_content = export_cap_xml_feed(items)
    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={"Content-Disposition": 'attachment; filename="alerts-cap-feed.xml"'},
    )


def _get(request: Request, alert_id: str) -> dict[str, Any]:
    a = get_store(request).alerts.get(alert_id)
    if a is None:
        raise ApiError(404, "ALERT_NOT_FOUND", "Alert not found", f"No alert with id {alert_id}.")
    return a


@router.get("/{alert_id}")
async def get_alert(request: Request, alert_id: str) -> dict[str, Any]:
    return envelope(_get(request, alert_id))


@router.get("/{alert_id}/geojson")
async def alert_as_geojson(request: Request, alert_id: str) -> JSONResponse:
    return JSONResponse(
        alert_geojson(_get(request, alert_id)),
        media_type="application/geo+json",
        headers={"Content-Disposition": f'attachment; filename="alert-{alert_id[:8]}.geojson"'},
    )


@router.get("/{alert_id}/xml")
async def alert_as_cap_xml(request: Request, alert_id: str) -> Response:
    """Export single alert as CAP-IN v1.2 XML format."""
    alert = _get(request, alert_id)
    xml_content = export_cap_xml(alert)
    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="alert-{alert_id[:8]}.xml"'},
    )


@router.post("/{alert_id}/disseminate")
async def disseminate_alert_endpoint(request: Request, alert_id: str) -> dict[str, Any]:
    """Trigger alert dissemination to all registered webhooks & email channels."""
    alert = _get(request, alert_id)
    result = await dissemination_service.disseminate_alert(alert)
    return envelope(result)


@router.get("/subscriptions/list", dependencies=[Depends(require_role("admin"))])
async def list_dissemination_subscriptions() -> dict[str, Any]:
    """List registered dissemination subscriptions (signing secrets are redacted)."""
    return envelope(dissemination_service.list_subscriptions())


@router.post("/subscriptions", dependencies=[Depends(require_role("admin"))])
async def add_dissemination_subscription(
    channel_type: Annotated[str, Body(embed=True)],
    target: Annotated[str, Body(embed=True)],
    secret: Annotated[str, Body(embed=True)] = "",
    severities: Annotated[list[str] | None, Body(embed=True)] = None,
) -> dict[str, Any]:
    """Register a new webhook URL or email endpoint for automated alert dissemination.

    When ``secret`` is omitted a random HMAC signing secret is generated and returned
    exactly once in this response; it is never returned by the list endpoint.
    """
    sub = dissemination_service.add_subscription(channel_type, target, secret, severities)
    payload: dict[str, Any] = {
        "id": sub.id,
        "channel_type": sub.channel_type,
        "target": sub.target,
        "severities": sub.severities,
        "status": "active",
    }
    if not secret:
        payload["secret"] = sub.secret
    return envelope(payload)
