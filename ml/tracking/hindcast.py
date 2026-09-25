"""Hindcast evaluation of track extrapolation: Kalman constant-velocity vs persistence.

For every origin step k >= 2 the filter is re-run on the measurements up to k and asked to predict steps
k+1..k+H; the prediction is compared with the *measured* centroid at that later step. Persistence
predicts "no movement" from the last measurement. Errors are great-circle km. This is a genuine
out-of-sample test of the extrapolation baseline (on whatever tracks it is given).
"""
from __future__ import annotations

import numpy as np

from ml.core.geometry import from_local_xy, haversine_km, to_local_xy
from ml.tracking.kalman import ConstantVelocityKalman
from ml.tracking.tracker import Track, TrackerConfig


def hindcast_extrapolation_errors(track: Track, cfg: TrackerConfig, max_horizon_steps: int = 3) -> dict[str, dict[int, float]]:
    """Mean error (km) per horizon step for ``kalman`` and ``persistence``, plus sample counts under ``n``."""
    pts = [p for p in track.points if p.observed]
    errs: dict[str, dict[int, list[float]]] = {"kalman": {}, "persistence": {}}
    for k in range(2, len(pts) - 1):
        origin = (pts[0].meas_lat, pts[0].meas_lon)
        kf = ConstantVelocityKalman(0.0, 0.0, cfg.sigma_meas_km, cfg.sigma_accel_kmh2, cfg.sigma_v0_kmh)
        for i in range(1, k + 1):
            kf.predict(pts[i].time_h - pts[i - 1].time_h)
            x, y = to_local_xy(pts[i].meas_lat, pts[i].meas_lon, *origin)
            kf.update(float(x), float(y))
        for h in range(1, max_horizon_steps + 1):
            if k + h >= len(pts):
                break
            xp, _ = kf.predicted(pts[k + h].time_h - pts[k].time_h)
            plat, plon = from_local_xy(xp[0], xp[1], *origin)
            truth = (pts[k + h].meas_lat, pts[k + h].meas_lon)
            errs["kalman"].setdefault(h, []).append(float(haversine_km(plat, plon, *truth)))
            errs["persistence"].setdefault(h, []).append(float(haversine_km(pts[k].meas_lat, pts[k].meas_lon, *truth)))
    out: dict[str, dict[int, float]] = {"kalman": {}, "persistence": {}, "n": {}}
    for name in ("kalman", "persistence"):
        for h, v in errs[name].items():
            out[name][h] = float(np.mean(v))
            out["n"][h] = float(len(v))
    return out
