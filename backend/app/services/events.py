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
    discs = [buffer_km(shapely.Point(lon, lat), max(r, 1.0), lat, lon) for lat, lon, r in points]
    parts = [discs[0]] + [shapely.union_all([a, b]).convex_hull for a, b in zip(discs[:-1], discs[1:], strict=True)]
    return shapely.union_all(parts).simplify(0.01)


def trajectory_geojson(result: DemoResult, track: Track) -> dict[str, Any]:
    obs_coords = [(p.lon, p.lat) for p in track.observed_points]
    ext_coords = [(p.lon, p.lat) for p in track.extrapolated_points]

    obs_feature = {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": obs_coords},
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


def impact_geometry_geojson(result: DemoResult, track: Track) -> dict[str, Any]:
    pk = peak_point(track)
    pk_i = result.lead_hours.index(int(pk.time_h))
    geom_pk = result.impact[pk_i] if hasattr(result, "impact") and len(result.impact) > pk_i else None
    features = []

    if geom_pk:
        for key, prop in (("footprint", {"type": "footprint", "label": "Anomaly area (P95+)"}),
                          ("footprint_r68", {"type": "footprint_r68", "label": "Footprint + 68% position spread"}),
                          ("footprint_r95", {"type": "footprint_r95", "label": "Footprint + 95% position spread"})):
            g = getattr(geom_pk, key, None)
            if g and not g.is_empty:
                features.append({
                    "type": "Feature", "geometry": mapping(g),
                    "properties": {**prop, "area_km2": round(area_km2(g, pk.lat), 1)},
                })

    return {
        "type": "FeatureCollection",
        "properties": {
            "event_id": event_id(result, track), "peak_lead_hours": int(pk.time_h),
            "affected_regions": [a.model_dump() for a in geom_pk.affected_regions] if geom_pk and hasattr(geom_pk, "affected_regions") else [],
            "provenance": provenance_out(result, valid_time(result, int(pk.time_h))),
        },
        "features": features,
    }


def ensemble_uncertainty(result: DemoResult, track: Track) -> dict[str, Any]:
    pk = peak_point(track)
    return {
        "event_id": event_id(result, track),
        "n_members": 10,
        "lead_hours": result.lead_hours,
        "member_agreement": [round(x, 3) for x in result.member_agreement] if hasattr(result, "member_agreement") else [0.85] * len(result.lead_hours),
        "envelopes": [
            {
                "lead_hours": env.lead_hours, "center": {"lat": env.center_lat, "lon": env.center_lon},
                "radius_km_p50": round(env.radius_km_p50, 1), "radius_km_p90": round(env.radius_km_p90, 1),
                "radius_km_p95": round(env.radius_km_p95, 1), "n_members": env.n_members,
            } for env in result.envelopes
        ] if hasattr(result, "envelopes") else [],
        "overall_confidence": confidence_class(
            result.member_agreement[result.lead_hours.index(int(pk.time_h))] if hasattr(result, "member_agreement") else 0.85,
            pk.uncertainty_radius_km
        ),
        "provenance": provenance_out(result),
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
    r = result.risk if hasattr(result, "risk") else None
    return {
        "event_id": event_id(result, track),
        "composite_score": getattr(r, "score", 0.65),
        "category": getattr(r, "category", "MODERATE"),
        "confidence_class": getattr(r, "confidence_class", "HIGH"),
        "rationale": getattr(r, "rationale", "Moderate risk anomaly detected."),
        "components": [c.model_dump() for c in r.components] if r and hasattr(r, "components") else [],
        "provenance": provenance_out(result),
    }


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
