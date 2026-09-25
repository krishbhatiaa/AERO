"""Regular latitude/longitude grid description.

Resolution is *metadata*, never a constant: the same code handles 0.25 deg ERA5, 0.12 deg IMDAA-like
grids, or 0.05 deg target grids. Coordinates refer to cell **centres**; latitudes ascend south to north.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from ml.core.geometry import EARTH_RADIUS_KM, KM_PER_DEG_LAT

FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class GridSpec:
    """Regular lat/lon grid (cell-centre coordinates)."""

    lat_min: float
    lon_min: float
    dlat: float
    dlon: float
    nlat: int
    nlon: int

    def __post_init__(self) -> None:
        if self.nlat < 1 or self.nlon < 1:
            raise ValueError("Grid must have at least one row and column")
        if self.dlat <= 0 or self.dlon <= 0:
            raise ValueError("Grid spacings must be positive")
        if not (-90.0 <= self.lat_min <= 90.0 and -90.0 <= self.lat_max <= 90.0):
            raise ValueError("Grid latitudes must lie within [-90, 90]")

    @property
    def lats(self) -> FloatArray:
        return self.lat_min + np.arange(self.nlat) * self.dlat

    @property
    def lons(self) -> FloatArray:
        return self.lon_min + np.arange(self.nlon) * self.dlon

    @property
    def lat_max(self) -> float:
        return self.lat_min + (self.nlat - 1) * self.dlat

    @property
    def lon_max(self) -> float:
        return self.lon_min + (self.nlon - 1) * self.dlon

    @property
    def shape(self) -> tuple[int, int]:
        return (self.nlat, self.nlon)

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """Outer cell-edge bounds ``(west, south, east, north)``."""
        return (
            self.lon_min - self.dlon / 2,
            self.lat_min - self.dlat / 2,
            self.lon_max + self.dlon / 2,
            self.lat_max + self.dlat / 2,
        )

    @property
    def is_global_lon(self) -> bool:
        """True when the grid wraps around the full 360 degrees of longitude."""
        return bool(abs(self.nlon * self.dlon - 360.0) < 1e-6 * self.dlon)

    def approx_resolution_km(self) -> tuple[float, float]:
        """(north-south, east-west at mid latitude) grid spacing in km."""
        mid = 0.5 * (self.lat_min + self.lat_max)
        return (self.dlat * KM_PER_DEG_LAT, self.dlon * KM_PER_DEG_LAT * float(np.cos(np.radians(mid))))

    def row_area_km2(self) -> FloatArray:
        """Exact spherical area of one cell for each latitude row (shape ``(nlat,)``)."""
        lat_lo = np.radians(np.clip(self.lats - self.dlat / 2, -90, 90))
        lat_hi = np.radians(np.clip(self.lats + self.dlat / 2, -90, 90))
        return np.asarray(EARTH_RADIUS_KM**2 * np.radians(self.dlon) * (np.sin(lat_hi) - np.sin(lat_lo)))

    def cell_area_km2(self) -> FloatArray:
        """Cell area for every cell, shape ``(nlat, nlon)``. Never use pixel counts as area."""
        return np.repeat(self.row_area_km2()[:, None], self.nlon, axis=1)

    def refined(self, factor: int) -> GridSpec:
        """Grid whose cells are ``factor`` x ``factor`` sub-cells of this grid's cells."""
        if factor < 1:
            raise ValueError("factor must be >= 1")
        dlat, dlon = self.dlat / factor, self.dlon / factor
        return GridSpec(
            lat_min=self.lat_min - self.dlat / 2 + dlat / 2,
            lon_min=self.lon_min - self.dlon / 2 + dlon / 2,
            dlat=dlat,
            dlon=dlon,
            nlat=self.nlat * factor,
            nlon=self.nlon * factor,
        )

    def fractional_index(self, lat: FloatArray, lon: FloatArray) -> tuple[FloatArray, FloatArray]:
        """Fractional (row, col) index of coordinates in this grid."""
        return (np.asarray(lat) - self.lat_min) / self.dlat, (np.asarray(lon) - self.lon_min) / self.dlon

    def to_dict(self) -> dict[str, float | int]:
        return {
            "lat_min": self.lat_min, "lon_min": self.lon_min, "dlat": self.dlat, "dlon": self.dlon,
            "nlat": self.nlat, "nlon": self.nlon,
        }


def block_mean(array: np.ndarray, factor: int) -> np.ndarray:
    """Average non-overlapping ``factor`` x ``factor`` blocks over the last two axes."""
    ny, nx = array.shape[-2:]
    if ny % factor or nx % factor:
        raise ValueError(f"Array shape {(ny, nx)} is not divisible by factor {factor}")
    new_shape = (*array.shape[:-2], ny // factor, factor, nx // factor, factor)
    return np.asarray(array.reshape(new_shape).mean(axis=(-3, -1)))
