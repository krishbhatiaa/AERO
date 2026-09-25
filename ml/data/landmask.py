"""Land/sea mask from Natural Earth country polygons (real geography, public domain).

Only the *static geography* is real; any weather field placed on top of it in the demo is synthetic and
labelled as such. When the boundary file is absent a documented analytic coastline is used instead.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import shape
from shapely.ops import unary_union

from ml.core.grid import GridSpec

DEFAULT_BOUNDARY = Path(__file__).resolve().parents[2] / "sample_data" / "boundaries" / "countries_domain.geojson"


def land_mask(grid: GridSpec, boundary_path: Path | None = None) -> tuple[np.ndarray, str]:
    """Return ``(mask, source)`` where mask is a float array (1 = land, 0 = sea) on ``grid``.

    ``source`` names the geography used so it can be recorded in provenance.
    """
    path = boundary_path or DEFAULT_BOUNDARY
    lon2d, lat2d = np.meshgrid(grid.lons, grid.lats)
    if path.is_file():
        feats = json.loads(path.read_text(encoding="utf-8"))["features"]
        land = unary_union([shape(f["geometry"]) for f in feats])
        shapely.prepare(land)
        mask = shapely.contains_xy(land, lon2d.ravel(), lat2d.ravel()).reshape(grid.shape)
        return mask.astype(np.float64), "Natural Earth 1:10m admin-0 (public domain)"
    # Fallback: analytic SW-NE coastline (fictional). Land lies west/north of the line.
    coast_lon = 85.0 + 0.35 * (lat2d - 18.0)
    return (lon2d < coast_lon).astype(np.float64), "analytic fictional coastline"
