"""Ensemble uncertainty utilities: field statistics, track envelopes and confidence classes.

Uncertainty sources are kept separate (initial-condition / ensemble members, downscaling samples, tracking
filter covariance). Nothing here turns an ensemble into a single certain answer.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ml.core.config import load_config
from ml.core.geometry import haversine_km


def ensemble_summary(members: np.ndarray, exceed_threshold: float | None = None) -> dict[str, np.ndarray]:
    """Per-cell statistics of ``members`` with shape ``(M, ny, nx)``: mean, median, std, p10, p90, p95, p99, exceed_prob."""
    if members.ndim != 3 or members.shape[0] < 2:
        raise ValueError("members must have shape (M>=2, ny, nx)")
    q = np.quantile(members, [0.1, 0.5, 0.9, 0.95, 0.99], axis=0)
    out = {"mean": members.mean(0), "median": q[1], "std": members.std(0, ddof=1),
           "p10": q[0], "p90": q[2], "p95": q[3], "p99": q[4]}
    if exceed_threshold is not None:
        out["exceed_prob"] = (members >= exceed_threshold).mean(0)
    return out


def mean_position(latlon: np.ndarray) -> tuple[float, float]:
    """Mean of (lat, lon) points computed on the sphere (safe across the antimeridian)."""
    phi, lam = np.radians(latlon[:, 0]), np.radians(latlon[:, 1])
    x, y, z = np.cos(phi) * np.cos(lam), np.cos(phi) * np.sin(lam), np.sin(phi)
    xm, ym, zm = x.mean(), y.mean(), z.mean()
    return float(np.degrees(np.arctan2(zm, np.hypot(xm, ym)))), float(np.degrees(np.arctan2(ym, xm)))


@dataclass(frozen=True)
class TrackEnvelope:
    """Ensemble position spread at one lead time."""

    mean_lat: float
    mean_lon: float
    radius_km_p90: float  # radius around the ensemble mean containing 90 % of members
    rms_spread_km: float
    n_members: int


def track_envelope(positions: np.ndarray) -> TrackEnvelope:
    """Summarise member positions ``(M, 2)`` as ``(lat, lon)``. Percentile envelope, NOT the NHC cone."""
    if positions.ndim != 2 or positions.shape[1] != 2 or positions.shape[0] < 2:
        raise ValueError("positions must have shape (M>=2, 2)")
    lat, lon = mean_position(positions)
    d = haversine_km(lat, lon, positions[:, 0], positions[:, 1])
    return TrackEnvelope(lat, lon, float(np.quantile(d, 0.9)), float(np.sqrt(np.mean(d**2))), int(positions.shape[0]))


def confidence_class(member_agreement: float, uncertainty_radius_km: float) -> str:
    """HIGH / MEDIUM / LOW using thresholds documented in ``config/risk.yaml`` (demonstration defaults)."""
    c = load_config("risk")["confidence"]
    hi, med = c["high"], c["medium"]
    if member_agreement >= hi["min_member_agreement"] and uncertainty_radius_km <= hi["max_uncertainty_radius_km"]:
        return "HIGH"
    if member_agreement >= med["min_member_agreement"] and uncertainty_radius_km <= med["max_uncertainty_radius_km"]:
        return "MEDIUM"
    return "LOW"
