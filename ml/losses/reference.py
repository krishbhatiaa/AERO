"""NumPy reference implementations of the training losses.

These are the *mathematical definitions* used for testing and for offline scoring. PyTorch training
ports (same formulas, autograd-enabled) are tracked in Batchsize.md; they must be tested against these.

ExtremeWeightedLoss  w(y) = 1 + alpha * max(0, (y - t) / scale)^beta ;  loss = mean(w(y) * base(pred, y))
    with base in {mse, mae, huber}. Cells whose truth exceeds threshold ``t`` are up-weighted, so a
    prediction of 80 for an actual 200 costs far more than the same error at an ordinary value.
"""
from __future__ import annotations

import numpy as np


def mse(pred: np.ndarray, target: np.ndarray) -> float:
    return float(np.mean((pred - target) ** 2))


def mae(pred: np.ndarray, target: np.ndarray) -> float:
    return float(np.mean(np.abs(pred - target)))


def huber(pred: np.ndarray, target: np.ndarray, delta: float = 1.0) -> float:
    e = np.abs(pred - target)
    return float(np.mean(np.where(e <= delta, 0.5 * e**2, delta * (e - 0.5 * delta))))


def quantile_loss(pred: np.ndarray, target: np.ndarray, tau: float) -> float:
    """Pinball loss for quantile ``tau`` in (0, 1)."""
    if not 0.0 < tau < 1.0:
        raise ValueError("tau must lie in (0, 1)")
    d = target - pred
    return float(np.mean(np.maximum(tau * d, (tau - 1.0) * d)))


def extreme_weights(target: np.ndarray, threshold: float, scale: float, alpha: float = 1.0, beta: float = 1.0) -> np.ndarray:
    if scale <= 0:
        raise ValueError("scale must be positive")
    return 1.0 + alpha * np.maximum(0.0, (target - threshold) / scale) ** beta


def extreme_weighted_loss(
    pred: np.ndarray, target: np.ndarray, threshold: float, scale: float, alpha: float = 1.0,
    beta: float = 1.0, base: str = "mse", delta: float = 1.0,
) -> float:
    """Extreme-aware loss (see module docstring)."""
    w = extreme_weights(target, threshold, scale, alpha, beta)
    if base == "mse":
        e = (pred - target) ** 2
    elif base == "mae":
        e = np.abs(pred - target)
    elif base == "huber":
        a = np.abs(pred - target)
        e = np.where(a <= delta, 0.5 * a**2, delta * (a - 0.5 * delta))
    else:
        raise ValueError(f"unknown base loss {base!r}")
    return float(np.mean(w * e))
