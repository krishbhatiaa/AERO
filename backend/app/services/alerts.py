"""AlertService: risk assessment + geospatial intersection -> alert records (decision support, not official warnings)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.services.events import DISCLAIMER, event_id, iso, peak_point, provenance_out, risk_out
from shapely.geometry import mapping

from ml.pipeline.real import RealResult as DemoResult, valid_time
from ml.tracking.tracker import Track

MODEL_VERSION = "baselines-v1.0"
_NS = uuid.UUID("a3c1f8d2-7b45-4e0a-9c6d-2f1b8e3d5a70")


def _track_probability(result: DemoResult, track: Track) -> float:
    """Intensity-weighted mean member agreement across all observed points of this track."""
    if not result.lead_hours or not result.member_agreement:
        return 0.5
    total_w, total_wv = 0.0, 0.0
    for p in track.observed_points:
        lead = int(p.time_h)
        if lead in result.lead_hours:
            idx = result.lead_hours.index(lead)
        else:
            idx = min(range(len(result.lead_hours)), key=lambda i: abs(result.lead_hours[i] - lead))
        agr = result.member_agreement[idx] if idx < len(result.member_agreement) else 0.0
        w = float(p.max_intensity or 1.0)
        total_w += w
        total_wv += agr * w
    if total_w == 0:
        return float(result.member_agreement[0]) if result.member_agreement else 0.5
    raw = total_wv / total_w
    # Boost very-low values slightly: real ERA5 tracks are genuine even at low ensemble agreement
    return max(raw, 0.15)


def build_alert(result: DemoResult, track: Track) -> dict[str, Any]:
    eid = event_id(result, track)
    obs = track.observed_points
    pk = peak_point(track)
    pk_lead = int(pk.time_h)
    if pk_lead not in result.impact and result.impact:
        pk_lead = min(result.impact.keys(), key=lambda k: abs(k - pk_lead))
    imp = result.impact.get(pk_lead) or {
        "regions_risk": [],
        "regions_impact": [],
        "geometries": {"risk": None, "impact": None, "uncertainty": None},
    }
    risk_regions = imp.get("regions_risk", [])
    names = [str(r["name"]) for r in risk_regions[:3]]
    if pk_lead in result.lead_hours:
        pk_i = result.lead_hours.index(pk_lead)
    elif result.lead_hours:
        pk_i = min(range(len(result.lead_hours)), key=lambda i: abs(result.lead_hours[i] - pk_lead))
    else:
        pk_i = 0
    env = result.envelopes[pk_i] if pk_i < len(result.envelopes) else None
    unc = env.radius_km_p90 if env else pk.uncertainty_radius_km
    start_lead = min(result.lead_hours, key=lambda h: abs(h - int(obs[0].time_h))) if result.lead_hours else int(obs[0].time_h)
    end_lead = min(result.lead_hours, key=lambda h: abs(h - int(obs[-1].time_h))) if result.lead_hours else int(obs[-1].time_h)
    start, end = valid_time(result, start_lead), valid_time(result, end_lead)
    return {
        "id": str(uuid.uuid5(_NS, f"{eid}/{result.risk.category}/{iso(start)}")),
        "event_id": eid, "event_type": "EXTREME_RAINFALL", "severity": result.risk.category, "severity_is_official": False,
        "location": {"centroid": {"lat": pk.lat, "lon": pk.lon}, "peak_lead_hours": int(pk.time_h),
                     "regions": names, "summary": ", ".join(names) if names else "over water / outside configured regions"},
        "affected_area": {"km2_footprint_max": max(p.area_km2 or 0.0 for p in obs), "regions_risk_polygon": risk_regions,
                          "regions_impact_polygon": imp["regions_impact"], "boundary_source": "Natural Earth admin-1 (not official)"},
        "forecast_window": {"start": iso(start), "end": iso(end), "timezone": "UTC"},
        "probability": _track_probability(result, track), "confidence": result.risk.confidence,
        "uncertainty": {"position_radius_km_p90": unc, "risk_polygon_buffer_km": unc * 0.617, "uncertainty_polygon_buffer_km": unc},
        "risk": risk_out(result),
        "source": "ERA5 reanalysis pipeline", "model_version": MODEL_VERSION,
        "data_kind": result.provenance.data_kind.value if hasattr(result, "provenance") and result.provenance else "REANALYSIS", "status": "ACTIVE", "created_at": iso(datetime.now(UTC)),
        "geometry": {"risk_polygon": mapping(imp["geometries"]["risk"]), "impact_polygon": mapping(imp["geometries"]["impact"]),
                     "uncertainty_polygon": mapping(imp["geometries"]["uncertainty"])},
        "verification": "Verify against official IMD products and State/District Disaster Management Authority bulletins before any action.",
        "disclaimer": DISCLAIMER, "provenance": provenance_out(result, valid_time(result, int(pk.time_h))),
    }


def alert_geojson(alert: dict[str, Any]) -> dict[str, Any]:
    """Export an alert as GeoJSON (three polygons + properties). Works offline; not a CAP document."""
    props = {k: alert[k] for k in ("id", "event_id", "event_type", "severity", "probability", "confidence", "forecast_window",
                                   "source", "model_version", "data_kind", "disclaimer", "created_at")}
    feats = [{"type": "Feature", "properties": {**props, "kind": kind}, "geometry": geom}
             for kind, geom in (("risk", alert["geometry"]["risk_polygon"]), ("impact", alert["geometry"]["impact_polygon"]),
                                ("uncertainty", alert["geometry"]["uncertainty_polygon"]))]
    return {"type": "FeatureCollection", "features": feats}
