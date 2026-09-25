"""Impact geometries and administrative-region intersection.

Polygons (all WGS84 lon/lat, buffers computed in a local azimuthal-equidistant projection so km are km):
* impact polygon      modelled anomaly footprint (or a geodesic circle of ``radius_km``)
* risk polygon        impact buffered by the 68 % position-uncertainty radius  R68 = R95 * sqrt(2.279/5.991)
* uncertainty polygon impact buffered by the 95 % position-uncertainty radius  R95

Region intersection: shapely STRtree for candidate search, areas in EPSG:6933 (equal-area) so km2 are
correct. PostGIS equivalents (ST_Intersects on GIST-indexed geometries) are documented in
``database/schema``; this in-process implementation serves the demo and unit tests.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from pyproj import CRS, Transformer
from shapely import STRtree
from shapely.geometry import Polygon, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform

from ml.core.geometry import circle_ring

R68_OVER_R95 = float(np.sqrt(2.279 / 5.991))  # chi-square(2 dof) quantiles


def _aeqd(lat0: float, lon0: float) -> tuple[Transformer, Transformer]:
    aeqd = CRS.from_proj4(f"+proj=aeqd +lat_0={lat0} +lon_0={lon0} +datum=WGS84 +units=m")
    wgs = CRS.from_epsg(4326)
    return Transformer.from_crs(wgs, aeqd, always_xy=True), Transformer.from_crs(aeqd, wgs, always_xy=True)


def buffer_km(geom: BaseGeometry, km: float, lat0: float, lon0: float) -> BaseGeometry:
    """Buffer a lon/lat geometry by ``km`` using a local azimuthal-equidistant projection."""
    if km < 0:
        raise ValueError("km must be non-negative")
    fwd, inv = _aeqd(lat0, lon0)
    return transform(inv.transform, transform(fwd.transform, geom).buffer(km * 1000.0, quad_segs=16))


def build_impact_geometries(
    centroid: tuple[float, float], radius_km: float, uncertainty_radius_km: float,
    footprint: BaseGeometry | None = None,
) -> dict[str, BaseGeometry]:
    """Return ``{"impact", "risk", "uncertainty"}`` polygons. ``centroid`` is (lat, lon)."""
    lat, lon = centroid
    impact = footprint if footprint is not None else Polygon(circle_ring(lat, lon, radius_km))
    return {
        "impact": impact,
        "risk": buffer_km(impact, uncertainty_radius_km * R68_OVER_R95, lat, lon),
        "uncertainty": buffer_km(impact, uncertainty_radius_km, lat, lon),
    }


_TO_EQUAL_AREA = Transformer.from_crs(CRS.from_epsg(4326), CRS.from_epsg(6933), always_xy=True)


def area_km2(geom: BaseGeometry) -> float:
    """Equal-area (EPSG:6933) area of a lon/lat geometry in km2."""
    return float(transform(_TO_EQUAL_AREA.transform, geom).area / 1e6)


@dataclass(frozen=True)
class Region:
    """An administrative region (state, district, ...)."""

    region_id: str
    name: str
    code: str
    level: str
    geometry: BaseGeometry


class RegionIndex:
    """Spatial index over administrative regions."""

    def __init__(self, regions: list[Region]) -> None:
        self.regions = regions
        self._tree = STRtree([r.geometry for r in regions]) if regions else None

    @classmethod
    def from_geojson(cls, path: Path, level: str = "state") -> RegionIndex:
        feats = json.loads(Path(path).read_text(encoding="utf-8"))["features"]
        regions = [
            Region(f"{level}:{f['properties'].get('code') or i}", str(f["properties"].get("name")),
                   str(f["properties"].get("code")), level, shape(f["geometry"]))
            for i, f in enumerate(feats)
        ]
        return cls(regions)

    def intersect(self, polygon: BaseGeometry) -> list[dict[str, float | str]]:
        """Regions intersecting ``polygon`` with intersection area and fractions, largest first."""
        if self._tree is None:
            return []
        poly_area = max(area_km2(polygon), 1e-9)
        out: list[dict[str, float | str]] = []
        for idx in self._tree.query(polygon, predicate="intersects"):
            reg = self.regions[int(idx)]
            part = reg.geometry.intersection(polygon)
            if part.is_empty:
                continue
            a = area_km2(part)
            out.append({
                "region_id": reg.region_id, "name": reg.name, "code": reg.code, "level": reg.level,
                "intersect_area_km2": a, "fraction_of_region": a / max(area_km2(reg.geometry), 1e-9),
                "fraction_of_polygon": a / poly_area,
            })
        out.sort(key=lambda d: float(d["intersect_area_km2"]), reverse=True)
        return out
