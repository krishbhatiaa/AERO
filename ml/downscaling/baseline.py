"""Baseline downscalers: nearest, bilinear, bicubic, and bicubic + conservation projection.

What   : Map a coarse field onto a finer grid without any learned component.
Why    : Every learned downscaler must beat these on extremes, spectra and CRPS to be promoted.
Input  : coarse 2-D array on ``coarse_grid`` and the target ``fine_grid``.
Output : fine 2-D array on ``fine_grid``.
Math   : spline interpolation of order 0/1/3 (scipy.ndimage.map_coordinates, edge-clamped). The
         ``bicubic_conservative`` variant clips to >= 0 (precipitation) and applies
         :func:`ml.physics.conservation.enforce_block_mean`.
Limits : Cubic splines use edge-clamped ('nearest') boundary handling, so values within ~2 coarse cells of the domain
         edge carry extra error (~4 % of the local gradient step at the very edge, <0.1 % beyond 4 cells).
         Interpolation cannot create sub-grid extremes: peaks are smoothed. That smoothing is exactly what
         the evaluation suite measures (peak error, P99 error, spectral ratio).
"""
from __future__ import annotations

from typing import Protocol

import numpy as np
from scipy import ndimage

from ml.core.grid import GridSpec
from ml.physics.conservation import enforce_block_mean

_ORDER = {"nearest": 0, "bilinear": 1, "bicubic": 3, "bicubic_conservative": 3}


class Downscaler(Protocol):
    """Interface implemented by baseline and learned downscalers."""

    name: str

    def downscale(self, coarse: np.ndarray, coarse_grid: GridSpec, fine_grid: GridSpec) -> np.ndarray: ...


def upsample(coarse: np.ndarray, coarse_grid: GridSpec, fine_grid: GridSpec, order: int) -> np.ndarray:
    """Interpolate ``coarse`` to the fine-grid cell centres with spline ``order`` (0, 1 or 3)."""
    if coarse.shape != coarse_grid.shape:
        raise ValueError(f"coarse shape {coarse.shape} != grid {coarse_grid.shape}")
    fi = (fine_grid.lats - coarse_grid.lat_min) / coarse_grid.dlat
    fj = (fine_grid.lons - coarse_grid.lon_min) / coarse_grid.dlon
    ii, jj = np.meshgrid(fi, fj, indexing="ij")
    return ndimage.map_coordinates(np.asarray(coarse, float), [ii, jj], order=order, mode="nearest")


class BaselineDownscaler:
    """Configurable interpolation baseline."""

    def __init__(self, method: str, nonneg: bool = True) -> None:
        if method not in _ORDER:
            raise ValueError(f"unknown method {method!r}; choose from {sorted(_ORDER)}")
        self.name = method
        self._method = method
        self._nonneg = nonneg

    def downscale(self, coarse: np.ndarray, coarse_grid: GridSpec, fine_grid: GridSpec) -> np.ndarray:
        fine = upsample(coarse, coarse_grid, fine_grid, _ORDER[self._method])
        if self._nonneg:
            fine = np.clip(fine, 0.0, None)
        if self._method == "bicubic_conservative":
            ratio = fine_grid.nlat / coarse_grid.nlat
            if abs(ratio - round(ratio)) > 1e-9 or abs(fine_grid.nlon / coarse_grid.nlon - ratio) > 1e-9:
                raise ValueError("conservation projection requires an integer grid ratio")
            fine = enforce_block_mean(fine, coarse, int(round(ratio)))
        return fine
