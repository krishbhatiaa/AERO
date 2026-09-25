"""Physical-consistency diagnostics for downscaled products.

Implemented (each has a unit test with an analytic answer):
* non-negativity of precipitation           fraction of cells with tp < 0
* coarse-cell conservation                   see :mod:`ml.physics.conservation`
* horizontal divergence of the 10 m wind     div V = (1/(R cos phi)) [d u / d lambda + d(v cos phi)/d phi]   [s-1]

The divergence is a *descriptive diagnostic*, not a proof of dynamical consistency: near-surface wind is
not non-divergent, and the moisture-budget diagnostic P - E = -div(q V) - dW/dt is listed as future work.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from ml.core.geometry import EARTH_RADIUS_KM
from ml.core.grid import GridSpec
from ml.physics.conservation import conservation_residual


def horizontal_divergence(u: np.ndarray, v: np.ndarray, grid: GridSpec) -> np.ndarray:
    """Horizontal divergence (s-1) of a wind field on a regular lat/lon grid (m s-1 inputs)."""
    r_m = EARTH_RADIUS_KM * 1000.0
    phi = np.radians(grid.lats)[:, None]
    dlam, dphi = np.radians(grid.dlon), np.radians(grid.dlat)
    du_dlam = np.gradient(u, dlam, axis=-1)
    dvcos_dphi = np.gradient(v * np.cos(phi), dphi, axis=-2)
    return np.asarray((du_dlam + dvcos_dphi) / (r_m * np.cos(phi)))


@dataclass(frozen=True)
class PhysicsReport:
    """Physics checks for one downscaled product."""

    nonneg_violation_fraction: float
    conservation_max_abs_mm: float
    conservation_max_rel: float
    wind_divergence_max_abs_s1: float | None
    wind_divergence_mean_abs_s1: float | None
    checks_passed: bool

    def to_dict(self) -> dict[str, float | bool | None]:
        return asdict(self)


def physics_report(
    fine_tp: np.ndarray, coarse_tp: np.ndarray, factor: int,
    u10: np.ndarray | None = None, v10: np.ndarray | None = None, wind_grid: GridSpec | None = None,
    conservation_tol_rel: float = 1e-3,
) -> PhysicsReport:
    """Run the implemented checks. Pass/fail covers only the hard constraints (non-negativity, conservation)."""
    neg = float(np.mean(fine_tp < 0.0))
    cons = conservation_residual(fine_tp, coarse_tp, factor)
    div_max = div_mean = None
    if u10 is not None and v10 is not None and wind_grid is not None:
        d = np.abs(horizontal_divergence(u10, v10, wind_grid))
        div_max, div_mean = float(d.max()), float(d.mean())
    return PhysicsReport(neg, cons["max_abs"], cons["max_rel"], div_max, div_mean,
                         bool(neg == 0.0 and cons["max_rel"] <= conservation_tol_rel))
