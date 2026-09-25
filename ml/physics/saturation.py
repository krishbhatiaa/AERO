"""Saturation vapour pressure and saturation specific humidity.

Definition (Bolton 1980, eq. 10):   e_s(T) = 6.112 * exp(17.67 T / (T + 243.5))      [hPa, T in degC]
Saturation specific humidity:        q_s = 0.622 e_s / (p - 0.378 e_s)                [kg/kg, p in hPa]
Assumptions: saturation over liquid water, valid roughly -35..35 degC; e_s <= p.
Reference: Bolton, D. (1980) Mon. Wea. Rev. 108, 1046-1053. Tests cross-check against MetPy, which uses a different
thermodynamically consistent formulation: agreement is within 0.3 % over -20..30 degC (not bit-identical).
"""
from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray


def saturation_vapor_pressure_hpa(t_celsius: ArrayLike) -> NDArray[np.float64]:
    t = np.asarray(t_celsius, float)
    return np.asarray(6.112 * np.exp(17.67 * t / (t + 243.5)))


def saturation_specific_humidity(t_celsius: ArrayLike, p_hpa: ArrayLike) -> NDArray[np.float64]:
    e = saturation_vapor_pressure_hpa(t_celsius)
    p = np.asarray(p_hpa, float)
    return np.asarray(0.622 * e / (p - 0.378 * e))


def saturation_violation_fraction(q: ArrayLike, t_celsius: ArrayLike, p_hpa: ArrayLike, tol: float = 1e-6) -> float:
    """Fraction of points where q exceeds q_s by more than ``tol`` (a soft physical-consistency check)."""
    qs = saturation_specific_humidity(t_celsius, p_hpa)
    return float(np.mean(np.asarray(q, float) > qs + tol))
