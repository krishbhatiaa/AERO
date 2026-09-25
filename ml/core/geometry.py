"""Spherical geometry helpers (great-circle distance, bearings, local tangent plane, circles).

All angles are degrees, all distances kilometres. Earth is modelled as a sphere of mean radius
``EARTH_RADIUS_KM`` (IUGG mean radius); this is adequate for tracking (<0.5 % distance error) and is
documented as a limitation for geodetic-grade work.
"""
from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray

EARTH_RADIUS_KM = 6371.0088
KM_PER_DEG_LAT = EARTH_RADIUS_KM * np.pi / 180.0

FloatArray = NDArray[np.float64]


def normalize_lon(lon: ArrayLike, convention: str = "-180_180") -> FloatArray:
    """Wrap longitudes to ``[-180, 180)`` or ``[0, 360)``."""
    arr = np.asarray(lon, dtype=np.float64)
    if convention == "-180_180":
        out = (arr + 180.0) % 360.0 - 180.0
        # float modulo can return exactly the upper bound for tiny negative inputs (e.g. -1e-23 % 360 == 360.0)
        return np.asarray(np.where(out >= 180.0, out - 360.0, out))
    if convention == "0_360":
        out = arr % 360.0
        return np.asarray(np.where(out >= 360.0, out - 360.0, out))
    raise ValueError(f"Unknown longitude convention: {convention!r}")


def haversine_km(lat1: ArrayLike, lon1: ArrayLike, lat2: ArrayLike, lon2: ArrayLike) -> FloatArray:
    """Great-circle distance in km (vectorised, broadcasting)."""
    p1, p2 = np.radians(np.asarray(lat1, float)), np.radians(np.asarray(lat2, float))
    dphi = p2 - p1
    dlmb = np.radians(np.asarray(lon2, float) - np.asarray(lon1, float))
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return np.asarray(2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0))))


def bearing_deg(lat1: ArrayLike, lon1: ArrayLike, lat2: ArrayLike, lon2: ArrayLike) -> FloatArray:
    """Initial bearing from point 1 to point 2, degrees clockwise from north in ``[0, 360)``."""
    p1, p2 = np.radians(np.asarray(lat1, float)), np.radians(np.asarray(lat2, float))
    dl = np.radians(np.asarray(lon2, float) - np.asarray(lon1, float))
    y = np.sin(dl) * np.cos(p2)
    x = np.cos(p1) * np.sin(p2) - np.sin(p1) * np.cos(p2) * np.cos(dl)
    return np.asarray(np.degrees(np.arctan2(y, x)) % 360.0)


def destination(
    lat: ArrayLike, lon: ArrayLike, bearing: ArrayLike, distance_km: ArrayLike
) -> tuple[FloatArray, FloatArray]:
    """Point reached travelling ``distance_km`` along ``bearing`` from (lat, lon)."""
    p1 = np.radians(np.asarray(lat, float))
    l1 = np.radians(np.asarray(lon, float))
    th = np.radians(np.asarray(bearing, float))
    d = np.asarray(distance_km, float) / EARTH_RADIUS_KM
    p2 = np.arcsin(np.sin(p1) * np.cos(d) + np.cos(p1) * np.sin(d) * np.cos(th))
    l2 = l1 + np.arctan2(np.sin(th) * np.sin(d) * np.cos(p1), np.cos(d) - np.sin(p1) * np.sin(p2))
    return np.degrees(p2), normalize_lon(np.degrees(l2))


def to_local_xy(lat: ArrayLike, lon: ArrayLike, lat0: float, lon0: float) -> tuple[FloatArray, FloatArray]:
    """Azimuthal-equidistant projection about (lat0, lon0): returns (east_km, north_km).

    Exact for the distance from the origin, so distances to the origin are preserved.
    """
    d = haversine_km(lat0, lon0, lat, lon)
    th = np.radians(bearing_deg(lat0, lon0, lat, lon))
    return np.asarray(d * np.sin(th)), np.asarray(d * np.cos(th))


def from_local_xy(x_km: ArrayLike, y_km: ArrayLike, lat0: float, lon0: float) -> tuple[FloatArray, FloatArray]:
    """Inverse of :func:`to_local_xy`."""
    x, y = np.asarray(x_km, float), np.asarray(y_km, float)
    d = np.hypot(x, y)
    th = np.degrees(np.arctan2(x, y)) % 360.0
    return destination(lat0, lon0, th, d)


def circle_ring(lat: float, lon: float, radius_km: float, n: int = 72) -> list[tuple[float, float]]:
    """Closed geodesic circle as ``[(lon, lat), ...]`` (GeoJSON order)."""
    if radius_km < 0:
        raise ValueError("radius_km must be non-negative")
    b = np.linspace(0.0, 360.0, n, endpoint=False)
    plat, plon = destination(lat, lon, b, radius_km)
    ring = [(float(x), float(y)) for x, y in zip(plon, plat, strict=True)]
    ring.append(ring[0])
    return ring
