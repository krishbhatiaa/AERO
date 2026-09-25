"""Unit conversions used by canonicalisation. All functions are pure and vectorised."""
from __future__ import annotations

from collections.abc import Callable

import numpy as np
from numpy.typing import ArrayLike, NDArray

STANDARD_GRAVITY = 9.80665  # m s-2 (CGPM 1901 conventional value)

FloatArray = NDArray[np.float64]


def kelvin_to_celsius(x: ArrayLike) -> FloatArray:
    return np.asarray(x, float) - 273.15


def celsius_to_kelvin(x: ArrayLike) -> FloatArray:
    return np.asarray(x, float) + 273.15


def metres_to_mm(x: ArrayLike) -> FloatArray:
    """Metres of liquid-water-equivalent to millimetres (ERA5 ``tp`` is in metres)."""
    return np.asarray(x, float) * 1000.0


def geopotential_to_height(x: ArrayLike) -> FloatArray:
    """Geopotential (m2 s-2) to geopotential height (m)."""
    return np.asarray(x, float) / STANDARD_GRAVITY


def pa_to_hpa(x: ArrayLike) -> FloatArray:
    return np.asarray(x, float) / 100.0


def hpa_to_pa(x: ArrayLike) -> FloatArray:
    return np.asarray(x, float) * 100.0


def ms_to_kmh(x: ArrayLike) -> FloatArray:
    return np.asarray(x, float) * 3.6


def ms_to_knots(x: ArrayLike) -> FloatArray:
    return np.asarray(x, float) * 1.943844492


_CONVERSIONS: dict[tuple[str, str], Callable[[ArrayLike], FloatArray]] = {
    ("K", "degC"): kelvin_to_celsius,
    ("degC", "K"): celsius_to_kelvin,
    ("m", "mm"): metres_to_mm,
    ("m2 s-2", "m"): geopotential_to_height,
    ("Pa", "hPa"): pa_to_hpa,
    ("hPa", "Pa"): hpa_to_pa,
    ("m s-1", "km h-1"): ms_to_kmh,
    ("m s-1", "kt"): ms_to_knots,
}


def convert(values: ArrayLike, from_unit: str, to_unit: str) -> FloatArray:
    """Convert ``values`` between registered unit pairs; identical units pass through unchanged."""
    if from_unit == to_unit:
        return np.asarray(values, float)
    try:
        return _CONVERSIONS[(from_unit, to_unit)](values)
    except KeyError:
        raise ValueError(f"No registered conversion from {from_unit!r} to {to_unit!r}") from None
