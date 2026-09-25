"""Coarse-cell conservation of accumulated quantities.

What   : Forces the (area-weighted) mean of every ``factor`` x ``factor`` block of a fine field to equal
         the corresponding coarse value, so downscaling redistributes rather than creates/destroys mass.
Math   : multiplicative:  f'_ij = f_ij * c_I / mean_I(f)            (keeps f >= 0 when f, c >= 0)
         additive:        f'_ij = f_ij + (c_I - mean_I(f))
         where I is the coarse cell containing fine cell ij. If mean_I(f) ~ 0 but c_I > 0 the coarse
         value is spread uniformly.
Units  : same as the field (e.g. mm of accumulated precipitation).
Assumes: the quantity is an accumulation/flux density whose coarse value is the area mean of the fine
         values. NOT valid for point-like fields such as temperature at a station or extrema.
Limits : the projection removes bias in block means only; it does not add fine-scale skill.
"""
from __future__ import annotations

import numpy as np

from ml.core.grid import block_mean


def _expand(coarse: np.ndarray, factor: int) -> np.ndarray:
    return np.repeat(np.repeat(coarse, factor, axis=-2), factor, axis=-1)


def block_weighted_mean(fine: np.ndarray, factor: int, weights: np.ndarray | None = None) -> np.ndarray:
    """Block mean of ``fine`` (optionally weighted by fine cell areas)."""
    if weights is None:
        return block_mean(fine, factor)
    return block_mean(fine * weights, factor) / block_mean(weights, factor)


def enforce_block_mean(
    fine: np.ndarray, coarse: np.ndarray, factor: int, mode: str = "multiplicative",
    weights: np.ndarray | None = None, eps: float = 1e-9,
) -> np.ndarray:
    """Project ``fine`` so that its block means equal ``coarse`` (see module docstring)."""
    if fine.shape[-2] != coarse.shape[-2] * factor or fine.shape[-1] != coarse.shape[-1] * factor:
        raise ValueError("fine and coarse shapes are inconsistent with factor")
    bm = block_weighted_mean(fine, factor, weights)
    if mode == "additive":
        return fine + _expand(coarse - bm, factor)
    if mode != "multiplicative":
        raise ValueError(f"unknown mode {mode!r}")
    ratio = np.where(bm > eps, coarse / np.where(bm > eps, bm, 1.0), 0.0)
    out = fine * _expand(ratio, factor)
    uniform = _expand(np.where(bm <= eps, coarse, 0.0), factor)
    return out + uniform


def conservation_residual(
    fine: np.ndarray, coarse: np.ndarray, factor: int, weights: np.ndarray | None = None
) -> dict[str, float]:
    """Diagnostics: max/mean absolute block-mean error and max relative error (relative to the coarse maximum)."""
    err = np.abs(block_weighted_mean(fine, factor, weights) - coarse)
    scale = max(float(np.abs(coarse).max()), 1e-12)
    return {"max_abs": float(err.max()), "mean_abs": float(err.mean()), "max_rel": float(err.max() / scale)}
