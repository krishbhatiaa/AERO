"""Anomaly detectors.

Three fully implemented strategies share one interface (:class:`AnomalyDetector`):

* :class:`ZScoreDetector`      Z = (X - mu) / sigma                       (Gaussian assumption, see limits)
* :class:`PercentileDetector`  approximate climatological percentile rank (distribution-free)
* :class:`EFIStyleDetector`    Extreme-Forecast-Index-style integral over an ensemble

Limits
------
* Z-scores assume a roughly symmetric distribution. Precipitation is strongly skewed: prefer the
  percentile or EFI-style detector for it.
* ``EFIStyleDetector`` implements the *published EFI formula* (Lalaurette 2003) against a
  climatology built here. It is **not** ECMWF's operational EFI (different model climate, resolution,
  post-processing) and is not validated against it.
* ``MLAnomalyDetector`` wraps any user-supplied scoring callable; no trained model ships with this repo.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from ml.climatology.service import Climatology
from ml.core.config import load_config


@dataclass(frozen=True)
class Thresholds:
    """Class boundaries applied to a detector's continuous score."""

    moderate: float
    extreme: float

    def __post_init__(self) -> None:
        if self.extreme < self.moderate:
            raise ValueError("extreme threshold must be >= moderate threshold")


class AnomalyDetector(Protocol):
    """Interface: turn a field (or ensemble) plus a climatology into a continuous anomaly score."""

    name: str
    thresholds: Thresholds

    def score(self, field: np.ndarray, clim: Climatology) -> np.ndarray: ...


def _cfg(name: str) -> dict:
    return load_config("anomaly")["detectors"][name]


def default_thresholds(name: str) -> Thresholds:
    """Documented default thresholds from ``config/anomaly.yaml``."""
    c = _cfg(name)
    return Thresholds(float(c["moderate"]), float(c["extreme"]))


class ZScoreDetector:
    """Z = (X - mu) / max(sigma, sigma_floor)."""

    name = "zscore"

    def __init__(self, thresholds: Thresholds | None = None, sigma_floor: float | None = None) -> None:
        self.thresholds = thresholds or default_thresholds("zscore")
        self.sigma_floor = float(sigma_floor if sigma_floor is not None else _cfg("zscore")["sigma_floor"])

    def score(self, field: np.ndarray, clim: Climatology) -> np.ndarray:
        return (np.asarray(field, float) - clim.mean) / np.maximum(clim.std, self.sigma_floor)


class PercentileDetector:
    """Approximate climatological percentile rank in [0, 1].

    Piecewise-linear interpolation between stored quantiles; ties take the upper rank; values above the
    highest stored quantile saturate smoothly towards 1 using the local top-tail spacing as scale.
    """

    name = "percentile"

    def __init__(self, thresholds: Thresholds | None = None) -> None:
        self.thresholds = thresholds or default_thresholds("percentile")

    def score(self, field: np.ndarray, clim: Climatology) -> np.ndarray:
        x = np.asarray(field, float)
        q, lv = clim.quantile_stack(), clim.levels
        k = q.shape[0]
        count = (q <= x[None, ...]).sum(axis=0)  # number of stored quantiles <= x
        idx = count - 1
        out = np.full(x.shape, lv[0])
        below = idx < 0
        top = idx >= k - 1
        mid = ~(below | top)
        i0 = np.clip(idx, 0, k - 2)
        q0 = np.take_along_axis(q, i0[None, ...], axis=0)[0]
        q1 = np.take_along_axis(q, (i0 + 1)[None, ...], axis=0)[0]
        span = q1 - q0
        frac = np.where(span > 0, (x - q0) / np.where(span > 0, span, 1.0), 0.0)
        out = np.where(mid, lv[i0] + np.clip(frac, 0.0, 1.0) * (lv[np.minimum(i0 + 1, k - 1)] - lv[i0]), out)
        scale = np.maximum(q[-1] - q[-2], 1e-9)
        tail = lv[-1] + (1.0 - lv[-1]) * (1.0 - np.exp(-np.maximum(x - q[-1], 0.0) / scale))
        out = np.where(top, tail, out)
        return np.where(np.isfinite(x), out, np.nan)


class EFIStyleDetector:
    """EFI-style index in [-1, 1] from an ensemble ``(members, lat, lon)``.

    EFI = (2/pi) * integral_0^1 (p - F_f(p)) / sqrt(p (1 - p)) dp        (Lalaurette 2003)
    Substituting p = sin^2(theta) gives dp / sqrt(p(1-p)) = 2 dtheta, hence
    EFI = (4/pi) * integral_0^{pi/2} (sin^2 theta - F_f(sin^2 theta)) dtheta,
    evaluated with the midpoint rule on ``n_theta`` nodes. F_f(p) is the ensemble fraction below the
    climatological p-quantile (ties count one half).
    """

    name = "efi_style"

    def __init__(self, thresholds: Thresholds | None = None, n_theta: int | None = None) -> None:
        self.thresholds = thresholds or default_thresholds("efi_style")
        self.n_theta = int(n_theta if n_theta is not None else _cfg("efi_style")["n_theta"])

    def score(self, field: np.ndarray, clim: Climatology) -> np.ndarray:
        members = np.asarray(field, float)
        if members.ndim == 2:  # a single deterministic field is a degenerate 1-member ensemble
            members = members[None, ...]
        n = self.n_theta
        theta = (np.arange(n) + 0.5) * (np.pi / (2.0 * n))
        p = np.sin(theta) ** 2
        acc = np.zeros(members.shape[1:], float)
        for pj in p:
            qj = clim.quantile_at(float(pj))
            below = (members < qj[None, ...]).mean(axis=0)
            ties = (members == qj[None, ...]).mean(axis=0)
            acc += pj - (below + 0.5 * ties)
        return np.clip(2.0 * acc / n, -1.0, 1.0)  # bounded in [-1, 1] mathematically; clip guards float rounding


class MLAnomalyDetector:
    """Adapter that exposes any scoring callable ``f(field, clim) -> score`` as an AnomalyDetector."""

    name = "ml"

    def __init__(self, model_fn: Callable[[np.ndarray, Climatology], np.ndarray], thresholds: Thresholds) -> None:
        self._fn = model_fn
        self.thresholds = thresholds

    def score(self, field: np.ndarray, clim: Climatology) -> np.ndarray:
        out = np.asarray(self._fn(field, clim), float)
        if out.shape != np.asarray(field).shape[-2:] and out.shape != np.asarray(field).shape:
            raise ValueError("ML detector output shape does not match the input grid")
        return out
