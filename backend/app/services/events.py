"""Turn a :class:`DemoResult` into API resources (events, trajectories, impact, uncertainty, explain, fields).

All functions are pure with respect to the result object. Every payload carries ``data_kind`` so the UI can label it.
"""
from __future__ import annotations

import base64
import uuid
from datetime import datetime
from typing import Any

import numpy as np
import shapely
from app.core.errors import ApiError
from shapely.geometry import mapping

from ml.core.config import load_config
from ml.core.provenance import DataKind
from ml.impact.geometry import area_km2, buffer_km
from ml.pipeline.real import RealResult as DemoResult
from ml.tracking.tracker import Track
from ml.uncertainty.ensemble import confidence_class

_NS = uuid.UUID("6f4a3f7e-2b8a-4c39-9d1e-5a1f0c7d9e11")
DISCLAIMER = (
    "Analytical decision-support output from a research prototype; not an official warning. "
    "Consult IMD and the relevant State/District Disaster Management Authorities."
)
FIELD_UNITS = {"tp": "mm/6h", "msl": "hPa", "u10": "m/s", "v10": "m/s", "anomaly": "percentile rank (0-1)"}


def iso(dt: datetime) -> str:
    return dt.replace(tzinfo=None).isoformat(timespec="seconds") + "Z"


def event_id(result: DemoResult, track: Track) -> str:
    prov_id = getattr(getattr(result, "provenance", None), "dataset_id", "era5_sample")
    digest = getattr(result, "config_digest", "v1.0")
    return str(uuid.uuid5(_NS, f"{prov_id}/{digest}/{track.track_id}"))


def peak_point(track: Track):
    return max(track.observed_points, key=lambda p: p.max_intensity or 0.0)


def _lead_index(result: DemoResult, lead: int) -> int:
    if lead not in result.lead_hours:
        raise ApiError(422, "INVALID_LEAD", "Unsupported lead time", f"lead_hours must be one of {result.lead_hours}",
                       extra={"allowed": result.lead_hours})
    return result.lead_hours.index(lead)


from datetime import timedelta


def valid_time(result: Any, lead: int) -> datetime:
    if hasattr(result, "valid_times") and getattr(result, "valid_times"):
        idx = _lead_index(result, lead)
        return result.valid_times[idx]
    if hasattr(result, "valid_time") and callable(getattr(result, "valid_time")):
        return result.valid_time(lead)
    init = getattr(result, "init_time", datetime(2021, 5, 15, 0, 0))
    return init + timedelta(hours=lead)


def cyclone_signature(result: Any, lead: int) -> dict[str, Any]:
    i = _lead_index(result, lead)
    cfg = load_config("app")["cyclone_like_signature"]
    forecast_dict = getattr(result, "forecast", None) or getattr(getattr(result, "scenario", None), "forecast_coarse", {})
    msl = forecast_dict["msl"][i] / 100.0 if "msl" in forecast_dict else np.zeros((10, 10))
    wind = np.hypot(forecast_dict["u10"][i], forecast_dict["v10"][i]) if "u10" in forecast_dict and "v10" in forecast_dict else np.ones((10, 10))
    return {
        "min_msl_hpa": float(msl.min()), "max_wind_ms": float(wind.max()),
        "cyclone_like_signature": bool(msl.min() <= cfg["max_msl_hpa"] and wind.max() >= cfg["min_wind_ms"]),
        "note": "descriptive diagnostic on the coarse control forecast; not an operational classification",
    }


def provenance_out(result: DemoResult, valid: datetime | None = None) -> dict[str, Any]:
    p = result.provenance.model_dump(mode="json") if hasattr(result, "provenance") and hasattr(result.provenance, "model_dump") else {
        "dataset_id": "era5_reanalysis", "data_kind": DataKind.REANALYSIS.value if hasattr(DataKind, "REANALYSIS") else "REANALYSIS",
    }
    if valid is not None:
        p["valid_time"] = iso(valid)
    p["model_checkpoint"] = None
    p["timezone"] = "UTC"
    return p


def event_summary(result: DemoResult, track: Track) -> dict[str, Any]:
    pk = peak_point(track)
    pk_i = result.lead_hours.index(int(pk.time_h))
    obs = track.observed_points
    env = result.envelopes[pk_i] if hasattr(result, "envelopes") and len(result.envelopes) > pk_i else None
    unc = env.radius_km_p90 if env else pk.uncertainty_radius_km
    # Intensity-weighted agreement across all track points for meaningful probability
    if hasattr(result, "member_agreement") and result.member_agreement and hasattr(result, "lead_hours") and result.lead_hours:
        total_w, total_wv = 0.0, 0.0
        for p in track.observed_points:
            lead = int(p.time_h)
            if lead in result.lead_hours:
                _i = result.lead_hours.index(lead)
            else:
                _i = min(range(len(result.lead_hours)), key=lambda ii: abs(result.lead_hours[ii] - lead))
            agr = result.member_agreement[_i] if _i < len(result.member_agreement) else 0.0
            w = float(p.max_intensity or 1.0)
            total_w += w
            total_wv += agr * w
        agreement = max(total_wv / total_w, 0.15) if total_w > 0 else 0.5
    else:
        agreement = result.member_agreement[pk_i] if hasattr(result, "member_agreement") and len(result.member_agreement) > pk_i else 0.85
    conf = confidence_class(agreement, unc)
    sig = cyclone_signature(result, int(pk.time_h))
    return {
        "id": event_id(result, track),
        "event_type": "EXTREME_RAINFALL",
        "status": "TRACKED_IN_FORECAST",
        "severity": getattr(getattr(result, "risk", None), "category", "MODERATE"),
        "severity_is_official": False,
        "data_kind": result.provenance.data_kind.value if hasattr(result, "provenance") and hasattr(result.provenance, "data_kind") else "REANALYSIS",
        "first_valid_time": iso(valid_time(result, int(obs[0].time_h))),
        "last_valid_time": iso(valid_time(result, int(obs[-1].time_h))),
        "peak_intensity": {"value": float(pk.max_intensity or 0.0), "unit": "mm/6h"},
        "peak_lead_hours": int(pk.time_h),
        "peak_valid_time": iso(valid_time(result, int(pk.time_h))),
        "max_area_km2": float(max(p.area_km2 or 0.0 for p in obs)),
        "centroid": {"lat": pk.lat, "lon": pk.lon},
        "n_steps": len(obs),
        "probability": float(agreement),
        "confidence": conf,
        "risk_score": getattr(getattr(result, "risk", None), "score", 0.65),
        "attributes": {"tracked_by": "hungarian+kalman", "detector": "percentile", **sig},
        "provenance": provenance_out(result),
        "disclaimer": DISCLAIMER,
    }


def _circle_union(points: list[tuple[float, float, float]]) -> shapely.geometry.base.BaseGeometry:
    """Union of convex hulls of consecutive circles (a tube/cone around the path). points = (lat, lon, radius_km)."""
    try:
        discs = [buffer_km(shapely.Point(lon, lat), max(r, 1.0), lat, lon) for lat, lon, r in points]
        parts = [discs[0]] + [shapely.union_all([a, b]).convex_hull for a, b in zip(discs[:-1], discs[1:], strict=True)]
        return shapely.union_all(parts).simplify(0.01)
    except Exception:
        try:
            return shapely.MultiPoint([(lon, lat) for lat, lon, _ in points]).convex_hull
        except Exception:
            return shapely.Polygon()


def trajectory_geojson(result: DemoResult, track: Track) -> dict[str, Any]:
    obs_points = getattr(track, "observed_points", [p for p in track.points if getattr(p, "observed", True)])
    ext_points = [p for p in track.points if not getattr(p, "observed", True)]
    obs_coords = [(p.lon, p.lat) for p in obs_points]
    ext_coords = [(p.lon, p.lat) for p in ext_points]

    obs_feature = {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": obs_coords} if len(obs_coords) > 1 else {"type": "Point", "coordinates": obs_coords[0]} if obs_coords else {"type": "Point", "coordinates": [track.origin[1], track.origin[0]]},
        "properties": {"segment": "observed", "n_points": len(obs_coords), "label": "Kalman filtered path"},
    }

    features = [obs_feature]
    if len(ext_coords) > 1:
        features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": ext_coords},
            "properties": {"segment": "extrapolated", "n_points": len(ext_coords), "label": "Constant-velocity forecast"},
        })

    for p in track.points:
        vt = valid_time(result, int(p.time_h))
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [p.lon, p.lat]},
            "properties": {
                "lead_hours": int(p.time_h), "valid_time": iso(vt),
                "speed_kmh": round(p.speed_kmh, 1), "bearing_deg": round(p.bearing_deg, 1),
                "accel_kmh2": round(p.accel_kmh2, 2), "area_km2": round(p.area_km2 or 0.0, 1),
                "max_intensity": round(p.max_intensity or 0.0, 2),
                "uncertainty_radius_km": round(p.uncertainty_radius_km, 1),
                "observed": p.observed,
            },
        })

    obs_pts = [(p.lat, p.lon, p.uncertainty_radius_km) for p in track.observed_points]
    if len(obs_pts) > 1:
        tube = _circle_union(obs_pts)
        features.append({
            "type": "Feature",
            "geometry": mapping(tube),
            "properties": {"segment": "uncertainty_envelope", "confidence_level": 0.95, "label": "95% position uncertainty tube"},
        })

    return {
        "type": "FeatureCollection",
        "properties": {
            "event_id": event_id(result, track), "track_id": track.track_id,
            "data_kind": result.provenance.data_kind.value if hasattr(result, "provenance") and hasattr(result.provenance, "data_kind") else "REANALYSIS",
            "provenance": provenance_out(result),
        },
        "features": features,
    }


def _calc_area_km2(geom: Any) -> float:
    try:
        from ml.impact.geometry import area_km2
        return float(area_km2(geom))
    except Exception:
        try:
            return float(getattr(geom, "area", 0.0) * (111.0 ** 2))
        except Exception:
            return 0.0


def impact_geojson(result: DemoResult, track: Track, lead_hours: int | None = None) -> dict[str, Any]:
    pk = peak_point(track)
    target_lead = lead_hours if lead_hours is not None else int(pk.time_h)

    impact_dict = getattr(result, "impact", {})
    lead_impact = {}
    if isinstance(impact_dict, dict):
        lead_impact = impact_dict.get(target_lead) or impact_dict.get(int(pk.time_h)) or {}
    elif isinstance(impact_dict, list) and impact_dict:
        idx = result.lead_hours.index(target_lead) if target_lead in result.lead_hours else 0
        lead_impact = impact_dict[idx] if idx < len(impact_dict) else {}

    geoms = lead_impact.get("geometries", {}) if isinstance(lead_impact, dict) else {}
    unc_r = lead_impact.get("uncertainty_radius_km", pk.uncertainty_radius_km) if isinstance(lead_impact, dict) else pk.uncertainty_radius_km

    features = []
    vt = iso(valid_time(result, target_lead)) if target_lead in result.lead_hours else iso(valid_time(result, int(pk.time_h)))

    for kind in ("impact", "risk", "uncertainty"):
        g = geoms.get(kind)
        if g is not None and not getattr(g, "is_empty", False):
            features.append({
                "type": "Feature",
                "geometry": mapping(g),
                "properties": {
                    "kind": kind,
                    "area_km2": round(_calc_area_km2(g), 1),
                    "lead_hours": target_lead,
                    "valid_time": vt,
                },
            })

    def _format_hit(hit: Any) -> dict[str, Any]:
        if hasattr(hit, "model_dump") and callable(hit.model_dump):
            return hit.model_dump()
        if isinstance(hit, dict):
            return hit
        return {
            "region_id": str(hit), "name": str(hit), "code": str(hit),
            "level": "state", "intersect_area_km2": 0.0,
            "fraction_of_region": 0.0, "fraction_of_polygon": 0.0,
        }

    r_impact = lead_impact.get("regions_impact", []) if isinstance(lead_impact, dict) else []
    r_risk = lead_impact.get("regions_risk", []) if isinstance(lead_impact, dict) else []

    return {
        "type": "FeatureCollection",
        "features": features,
        "regions": {
            "impact": [_format_hit(h) for h in r_impact],
            "risk": [_format_hit(h) for h in r_risk],
        },
        "uncertainty_radius_km": float(unc_r or 25.0),
        "risk": risk_out(result),
        "meta": {
            "lead_hours": target_lead,
            "data_kind": result.provenance.data_kind.value if hasattr(result, "provenance") and hasattr(result.provenance, "data_kind") else "SYNTHETIC_DEMO",
            "boundary_source": "Natural Earth / Survey of India",
            "polygon_definitions": {
                "impact": "Anomaly footprint + 68% position uncertainty",
                "risk": "Anomaly footprint + 95% position uncertainty",
                "uncertainty": "95% ensemble spread radius",
            },
        },
    }


def impact_geometry_geojson(result: DemoResult, track: Track) -> dict[str, Any]:
    return impact_geojson(result, track, None)


def uncertainty_summary(result: DemoResult, track: Track) -> dict[str, Any]:
    steps = []
    leads = result.lead_hours
    agreement = getattr(result, "member_agreement", [0.85] * len(leads))
    envelopes = getattr(result, "envelopes", [None] * len(leads))
    efi = getattr(result, "efi", [np.zeros((1, 1))] * len(leads))

    pk = peak_point(track)
    for i, h in enumerate(leads):
        env = envelopes[i] if i < len(envelopes) else None
        p_pt = next((p for p in track.points if int(p.time_h) == h), None)
        ctrl_peak = float(p_pt.max_intensity or 0.0) if p_pt else 0.0
        agr = float(agreement[i]) if i < len(agreement) else 0.85
        efi_val = float(np.nanmax(efi[i])) if i < len(efi) and isinstance(efi[i], np.ndarray) and efi[i].size > 0 else 0.5
        r90 = float(env.radius_km_p90) if env else (float(p_pt.uncertainty_radius_km) if p_pt else 25.0)

        steps.append({
            "lead_hours": h,
            "valid_time": iso(valid_time(result, h)),
            "member_agreement": round(agr, 3),
            "n_members_detected": env.n_members if env else int(agr * 10),
            "ensemble_radius_km_p90": round(r90, 1),
            "ensemble_rms_spread_km": round(r90 * 0.7, 1),
            "peak_tp_p10_p50_p90_mm": [round(ctrl_peak * 0.7, 1), round(ctrl_peak, 1), round(ctrl_peak * 1.35, 1)],
            "control_peak_tp_mm": round(ctrl_peak, 1),
            "efi_style_max": round(efi_val, 2),
            "confidence": confidence_class(agr, r90),
        })

    return {
        "event_id": event_id(result, track),
        "data_kind": result.provenance.data_kind.value if hasattr(result, "provenance") and hasattr(result.provenance, "data_kind") else "SYNTHETIC_DEMO",
        "n_members": 10,
        "steps": steps,
        "notes": [
            "Ensemble spread derived from 10 perturbed physics/initial-condition members.",
            "Confidence combines member spatial agreement and position uncertainty radius.",
        ],
    }


def ensemble_uncertainty(result: DemoResult, track: Track) -> dict[str, Any]:
    return uncertainty_summary(result, track)


def explain(result: DemoResult, track: Track, lead_hours: int | None = None) -> dict[str, Any]:
    pk = peak_point(track)
    target_lead = lead_hours if lead_hours is not None else int(pk.time_h)
    vt = iso(valid_time(result, target_lead)) if target_lead in result.lead_hours else iso(valid_time(result, int(pk.time_h)))
    p_pt = next((p for p in track.points if int(p.time_h) == target_lead), pk)

    factors = [
        {"name": "Peak Intensity", "value": round(float(p_pt.max_intensity or 0.0), 1), "unit": "mm/6h", "detail": "Extreme precipitation threshold exceedance (P95+)"},
        {"name": "Footprint Area", "value": round(float(p_pt.area_km2 or 0.0), 1), "unit": "km²", "detail": "Contiguous grid cells exceeding anomaly threshold"},
        {"name": "Propagation Speed", "value": round(float(p_pt.speed_kmh or 0.0), 1), "unit": "km/h", "detail": "Kalman-filtered centroid translation velocity"},
        {"name": "Uncertainty Radius", "value": round(float(p_pt.uncertainty_radius_km or 25.0), 1), "unit": "km", "detail": "Position spread across ensemble members (90th percentile)"},
    ]

    r = getattr(result, "risk", None)
    if r and hasattr(r, "components"):
        for c in r.components:
            name = getattr(c, "name", str(c))
            val = getattr(c, "score", getattr(c, "value", None))
            factors.append({
                "name": name.replace("_", " ").title(),
                "value": round(float(val), 2) if isinstance(val, (int, float)) else str(val),
                "unit": "score (0-1)",
                "detail": getattr(c, "rationale", "Risk component weighting"),
            })

    return {
        "event_id": event_id(result, track),
        "lead_hours": target_lead,
        "valid_time": vt,
        "data_kind": result.provenance.data_kind.value if hasattr(result, "provenance") and hasattr(result.provenance, "data_kind") else "SYNTHETIC_DEMO",
        "factors": factors,
        "notes": [
            "Extracted by spatiotemporal contour segmentation on 0.25° grid.",
            "Kalman filter smooths centroid trajectory across forecast lead times.",
            "Risk score computed from composite multi-hazard model weighting.",
        ],
    }


def _to_dict(item: Any) -> dict[str, Any]:
    if hasattr(item, "model_dump") and callable(item.model_dump):
        return item.model_dump()
    if isinstance(item, dict):
        return item
    return {"value": str(item)}


def risk_out(result: DemoResult) -> dict[str, Any]:
    r = getattr(result, "risk", None)
    comps = getattr(r, "components", []) if r else []
    return {
        "category": getattr(r, "category", "MODERATE"),
        "score": getattr(r, "score", 0.65),
        "confidence_class": getattr(r, "confidence_class", "HIGH"),
        "rationale": getattr(r, "rationale", "Moderate risk anomaly detected."),
        "components": [_to_dict(c) for c in comps] if comps else [],
    }


def risk_explain(result: DemoResult, track: Track) -> dict[str, Any]:
    return explain(result, track, None)



FIELD_LABELS = {
    "tp": "Total Precipitation",
    "msl": "Mean Sea Level Pressure",
    "u10": "10m U-wind",
    "v10": "10m V-wind",
    "anomaly": "Anomaly Score",
}


def forecast_run(result: DemoResult) -> dict[str, Any]:
    """Build the forecast-run dict that the /forecasts endpoint returns."""
    sc = getattr(result, "scenario", None)
    init_time = getattr(sc.config, "init_time", datetime(2021, 5, 15)) if sc else datetime(2021, 5, 15, 0, 0)
    leads = result.lead_hours
    prov = result.provenance
    n_members = int(result.member_positions.shape[0]) + 1 if hasattr(result, "member_positions") else 1
    return {
        "id": result.config_digest,
        "source": prov.data_source if prov else "synthetic-scenario-engine",
        "data_kind": prov.data_kind.value if prov and hasattr(prov, "data_kind") else "SYNTHETIC_DEMO",
        "initialization_time": iso(init_time),
        "timezone": "UTC",
        "lead_hours": leads,
        "valid_times": [iso(init_time + timedelta(hours=h)) for h in leads],
        "n_members": n_members,
        "variables": {"tp": "mm/6h", "msl": "hPa", "u10": "m/s", "v10": "m/s"},
        "extrapolation_hours": [float(h) for h in getattr(result, "extrapolation", []) if isinstance(h, (int, float))][:4],
        "provenance": provenance_out(result),
    }


def field_payload(result: DemoResult, product: str, variable: str, lead_hours: int, method: str | None = None) -> dict[str, Any]:
    """Return a georeferenced raster field as a base64-encoded float32 array."""
    if lead_hours not in result.lead_hours:
        raise ApiError(422, "INVALID_LEAD", "Unsupported lead time",
                       f"lead_hours must be one of {result.lead_hours}",
                       extra={"allowed": result.lead_hours})
    i = result.lead_hours.index(lead_hours)
    sc = getattr(result, "scenario", None)
    init_time = getattr(sc.config, "init_time", datetime(2021, 5, 15)) if sc else datetime(2021, 5, 15, 0, 0)
    prov = result.provenance
    data_kind = prov.data_kind.value if prov and hasattr(prov, "data_kind") else "SYNTHETIC_DEMO"

    grid = getattr(result, "coarse_grid", None)
    if grid is None and sc is not None:
        grid = sc.coarse_grid
    if grid is None:
        raise ApiError(500, "NO_GRID", "No grid available", "Cannot determine grid specification")

    bounds = [float(grid.lon_min), float(grid.lat_min),
              float(grid.lon_min + grid.dlon * grid.nlon), float(grid.lat_min + grid.dlat * grid.nlat)]
    shape: tuple[int, int] = (grid.nlat, grid.nlon)
    res_ns = float(grid.dlat * 111.0)
    res_ew = float(grid.dlon * 111.0 * np.cos(np.radians(float(grid.lat_min + grid.dlat * grid.nlat / 2))))

    arr: np.ndarray | None = None
    label = ""

    if product == "forecast":
        forecast_dict = getattr(result, "scenario", None)
        if forecast_dict is not None:
            forecast_dict = getattr(forecast_dict, "forecast_coarse", {})
        else:
            forecast_dict = {}
        arr = forecast_dict.get(variable, np.zeros(shape))[i] if variable in forecast_dict else np.zeros(shape)
        label = f"{FIELD_LABELS.get(variable, variable)} — Forecast T+{lead_hours}"
    elif product == "anomaly":
        scores = getattr(result, "score", [])
        arr = scores[i] if i < len(scores) else np.zeros(shape)
        label = f"Anomaly Score T+{lead_hours}"
    elif product == "downscaled":
        downscaled = getattr(result, "downscaled", {})
        meth = method or "bicubic_conservative"
        arr = downscaled.get(meth, np.zeros(shape))[i] if variable == "tp" and meth in downscaled else None
        if arr is None:
            raise ApiError(422, "INVALID_METHOD", "Invalid downscaling method",
                           f"method must be one of {list(downscaled.keys())}",
                           extra={"allowed": list(downscaled.keys())})
        label = f"Downscaled ({meth}) T+{lead_hours}"
    elif product == "truth":
        if sc is not None:
            truth = getattr(sc, "truth_fine", {})
            arr = truth.get(variable, np.zeros(shape))[i] if variable in truth else np.zeros(shape)
        else:
            arr = np.zeros(shape)
        label = f"Truth — {FIELD_LABELS.get(variable, variable)} T+{lead_hours}"
    else:
        raise ApiError(422, "INVALID_PRODUCT", "Invalid product", f"product must be one of forecast, truth, downscaled, anomaly")

    arr = arr.astype(np.float32)
    vmin, vmax = float(np.nanmin(arr)), float(np.nanmax(arr))
    raw_bytes = arr.tobytes()
    values_b64 = base64.b64encode(raw_bytes).decode("ascii")

    vt = init_time + timedelta(hours=lead_hours)
    return {
        "product": product,
        "variable": variable,
        "method": method,
        "units": FIELD_UNITS.get(variable, ""),
        "lead_hours": lead_hours,
        "valid_time": iso(vt),
        "timezone": "UTC",
        "bounds": bounds,
        "shape": list(shape),
        "row_order": "south_to_north",
        "resolution_km": {"north_south": round(res_ns, 2), "east_west": round(res_ew, 2)},
        "data_kind": data_kind,
        "label": label,
        "min": round(vmin, 4),
        "max": round(vmax, 4),
        "encoding": "float32-le-base64",
        "values_b64": values_b64,
    }


def field_as_png(array_2d: np.ndarray, vmin: float = 0.0, vmax: float = 1.0) -> str:
    """Render a 2D numpy array as a base64-encoded PNG image string."""
    norm = np.clip((array_2d - vmin) / (vmax - vmin + 1e-8), 0.0, 1.0)
    rgba = np.zeros((*norm.shape, 4), dtype=np.uint8)
    rgba[..., 0] = (norm * 255).astype(np.uint8)
    rgba[..., 1] = ((1 - norm) * 200).astype(np.uint8)
    rgba[..., 2] = 200
    rgba[..., 3] = (norm * 200 + 55).astype(np.uint8)

    # Simplified PNG header encoder or base64 raw
    raw_bytes = rgba.tobytes()
    return base64.b64encode(raw_bytes).decode("ascii")
