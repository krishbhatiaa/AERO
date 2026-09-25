"""Evaluation metrics: general, extremes, spatial, spectral, probabilistic, tracking, bootstrap.

Never evaluate with RMSE alone. Every metric below is a pure function with a documented definition;
sign conventions: ``error = prediction - truth`` (negative = under-prediction).
"""
from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np
from scipy import ndimage

from ml.core.geometry import haversine_km
from ml.core.grid import GridSpec

# ---------------------------------------------------------------- general


def mae(pred: np.ndarray, truth: np.ndarray) -> float:
    return float(np.mean(np.abs(pred - truth)))


def rmse(pred: np.ndarray, truth: np.ndarray) -> float:
    return float(np.sqrt(np.mean((pred - truth) ** 2)))


def bias(pred: np.ndarray, truth: np.ndarray) -> float:
    return float(np.mean(pred - truth))


def correlation(pred: np.ndarray, truth: np.ndarray) -> float:
    p, t = pred.ravel(), truth.ravel()
    if p.std() < 1e-12 or t.std() < 1e-12:
        return float("nan")
    return float(np.corrcoef(p, t)[0, 1])


# ---------------------------------------------------------------- extremes


def _exceeds(values: np.ndarray, truth: np.ndarray, q: float) -> np.ndarray:
    """Boolean mask of ``values`` at/above the q-quantile of ``truth``.

    For zero-inflated fields (precipitation) the quantile itself can equal the minimum (e.g. 0 mm); every truth
    cell would then count as "extreme". In that case the comparison is strict (``>``) instead of ``>=``. The same
    rule is applied to predictions and truth so recall/precision stay comparable.
    """
    thr = np.quantile(truth, q)
    strict = bool((truth >= thr).all())
    return values > thr if strict else values >= thr


def peak_error(pred: np.ndarray, truth: np.ndarray) -> float:
    """max(pred) - max(truth)."""
    return float(pred.max() - truth.max())


def extreme_value_bias(pred: np.ndarray, truth: np.ndarray, q: float = 0.99) -> float:
    """Mean (pred - truth) over cells where truth >= its q-quantile (bias *conditional on* extremes)."""
    m = _exceeds(truth, truth, q)
    return float(np.mean(pred[m] - truth[m])) if m.any() else float("nan")


def quantile_error(pred: np.ndarray, truth: np.ndarray, q: float) -> float:
    """quantile_q(pred) - quantile_q(truth); q=0.95 -> 'P95 error', q=0.99 -> 'P99 error'."""
    return float(np.quantile(pred, q) - np.quantile(truth, q))


def extreme_recall_precision(pred: np.ndarray, truth: np.ndarray, q: float = 0.99) -> tuple[float, float]:
    """Recall/precision of exceeding the truth's q-quantile threshold (see :func:`_exceeds`)."""
    t, p = _exceeds(truth, truth, q), _exceeds(pred, truth, q)
    hits = float(np.sum(t & p))
    return hits / max(float(t.sum()), 1.0), hits / max(float(p.sum()), 1.0)


# ---------------------------------------------------------------- spatial


def iou(a: np.ndarray, b: np.ndarray) -> float:
    inter, union = np.sum(a & b), np.sum(a | b)
    return float(inter / union) if union else float("nan")


def centroid_distance_km(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    return float(haversine_km(lat_a, lon_a, lat_b, lon_b))


def area_error_km2(a: np.ndarray, b: np.ndarray, grid: GridSpec) -> float:
    area = grid.cell_area_km2()
    return float(area[a].sum() - area[b].sum())


def boundary_error_km(a: np.ndarray, b: np.ndarray, grid: GridSpec) -> float:
    """Symmetric mean boundary distance (Chamfer) between two masks, in km."""
    if not a.any() or not b.any():
        return float("nan")
    ba = a & ~ndimage.binary_erosion(a)
    bb = b & ~ndimage.binary_erosion(b)
    km = float(np.mean(grid.approx_resolution_km()))
    da = ndimage.distance_transform_edt(~bb)[ba].mean()
    db = ndimage.distance_transform_edt(~ba)[bb].mean()
    return float(0.5 * (da + db) * km)


# ---------------------------------------------------------------- spectral


def radial_psd(field: np.ndarray, dx_km: float) -> tuple[np.ndarray, np.ndarray]:
    """Radially averaged power spectral density. Returns (wavelength_km, power), longest wavelength first."""
    f = field - field.mean()
    win = np.outer(np.hanning(f.shape[0]), np.hanning(f.shape[1]))
    power = np.abs(np.fft.fft2(f * win)) ** 2
    ky = np.fft.fftfreq(f.shape[0], d=dx_km)
    kx = np.fft.fftfreq(f.shape[1], d=dx_km)
    k = np.hypot(*np.meshgrid(kx, ky))
    kmin = 1.0 / (dx_km * max(f.shape))
    edges = np.arange(kmin, 0.5 / dx_km + kmin, kmin)
    idx = np.digitize(k.ravel(), edges)
    sums = np.bincount(idx, weights=power.ravel(), minlength=len(edges) + 1)[1 : len(edges)]
    counts = np.bincount(idx, minlength=len(edges) + 1)[1 : len(edges)]
    centres = 0.5 * (edges[:-1] + edges[1:])
    ok = counts > 0
    return 1.0 / centres[ok], sums[ok] / counts[ok]


def band_power_ratio(pred: np.ndarray, truth: np.ndarray, dx_km: float, band_km: tuple[float, float]) -> float:
    """Sum of PSD of ``pred`` over wavelengths in ``band_km`` divided by that of ``truth``.

    1 means the fine-scale variance is fully recovered; << 1 means the prediction is smoothed.
    """
    wl, pp = radial_psd(pred, dx_km)
    _, pt = radial_psd(truth, dx_km)
    m = (wl >= band_km[0]) & (wl <= band_km[1])
    denom = pt[m].sum()
    return float(pp[m].sum() / denom) if denom > 0 else float("nan")


# ---------------------------------------------------------------- probabilistic


def crps_ensemble(members: np.ndarray, obs: np.ndarray) -> float:
    """Fair CRPS (Ferro 2014) of an ensemble ``(M, ...)`` against ``obs``: mean|x-y| - sum|xi-xj| / (2M(M-1))."""
    m = members.shape[0]
    if m < 2:
        raise ValueError("fair CRPS needs at least 2 members")
    term1 = np.mean(np.abs(members - obs[None, ...]), axis=0)
    diffs = np.abs(members[:, None, ...] - members[None, :, ...]).sum(axis=(0, 1))
    return float(np.mean(term1 - diffs / (2.0 * m * (m - 1))))


def reliability_curve(prob: np.ndarray, outcome: np.ndarray, n_bins: int = 10) -> dict[str, list[float]]:
    """Reliability diagram data: mean forecast probability vs observed frequency per bin."""
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.clip(np.digitize(prob.ravel(), edges) - 1, 0, n_bins - 1)
    o = outcome.ravel().astype(float)
    p = prob.ravel()
    fp, of, cnt = [], [], []
    for b in range(n_bins):
        sel = idx == b
        cnt.append(float(sel.sum()))
        fp.append(float(p[sel].mean()) if sel.any() else float("nan"))
        of.append(float(o[sel].mean()) if sel.any() else float("nan"))
    return {"forecast_probability": fp, "observed_frequency": of, "count": cnt}


def expected_calibration_error(prob: np.ndarray, outcome: np.ndarray, n_bins: int = 10) -> float:
    r = reliability_curve(prob, outcome, n_bins)
    cnt = np.array(r["count"])
    fp, of = np.array(r["forecast_probability"]), np.array(r["observed_frequency"])
    ok = cnt > 0
    return float(np.sum(cnt[ok] * np.abs(fp[ok] - of[ok])) / cnt.sum())


def interval_coverage(lower: np.ndarray, upper: np.ndarray, obs: np.ndarray) -> float:
    """Fraction of observations inside [lower, upper]."""
    return float(np.mean((obs >= lower) & (obs <= upper)))


# ---------------------------------------------------------------- tracking


def trajectory_error_km(pred: Sequence[tuple[float, float]], truth: Sequence[tuple[float, float]]) -> float:
    """Mean great-circle error between corresponding (lat, lon) points."""
    if len(pred) != len(truth) or not pred:
        raise ValueError("pred and truth must be equal-length, non-empty sequences")
    return float(np.mean([haversine_km(p[0], p[1], t[0], t[1]) for p, t in zip(pred, truth, strict=True)]))


def displacement_error_km(pred: Sequence[tuple[float, float]], truth: Sequence[tuple[float, float]]) -> float:
    """Error of the total displacement vector (first -> last point) in km."""
    (pl0, po0), (pl1, po1) = pred[0], pred[-1]
    (tl0, to0), (tl1, to1) = truth[0], truth[-1]
    dp_e = haversine_km(pl0, po0, pl0, po1) * np.sign(po1 - po0)
    dp_n = haversine_km(pl0, po0, pl1, po0) * np.sign(pl1 - pl0)
    dt_e = haversine_km(tl0, to0, tl0, to1) * np.sign(to1 - to0)
    dt_n = haversine_km(tl0, to0, tl1, to0) * np.sign(tl1 - tl0)
    return float(np.hypot(dp_e - dt_e, dp_n - dt_n))


def track_continuity(observed_flags: Sequence[bool]) -> float:
    """Fraction of frames in a track that were detected (not coasted)."""
    return float(np.mean(observed_flags)) if len(observed_flags) else float("nan")


def detection_rate(n_detected: int, n_expected: int) -> float:
    return float(n_detected / n_expected) if n_expected else float("nan")


# ---------------------------------------------------------------- bootstrap


def bootstrap_ci(
    values: Sequence[float], stat: Callable[[np.ndarray], float] = np.mean, n: int = 2000, seed: int = 0,
    alpha: float = 0.05,
) -> tuple[float, float]:
    """Percentile bootstrap CI of ``stat`` over ``values`` (resample frames, not pixels)."""
    v = np.asarray(values, float)
    rng = np.random.default_rng(seed)
    samples = [stat(v[rng.integers(0, len(v), len(v))]) for _ in range(n)]
    return float(np.quantile(samples, alpha / 2)), float(np.quantile(samples, 1 - alpha / 2))
