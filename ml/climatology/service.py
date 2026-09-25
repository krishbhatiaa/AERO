"""Climatological baseline: mean, std, median and quantiles over a configurable period.

What   : Distribution of a variable under "normal" conditions for a given time of year.
Why    : Anomalies are only meaningful relative to a climatology. The period (e.g. 1991-2020) and the
         seasonal pooling window are parameters - never hard-coded.
Input  : ``xarray.DataArray`` with a ``time`` dimension (may be Dask-backed and lazy).
Output : :class:`Climatology` holding ``mean``, ``std`` and ``quantile(level, lat, lon)`` fields.
Math   : For target day-of-year d, sample S = {x(t) : year(t) in period, |doy(t) - d| <= w (circular)}.
         mean/std(ddof=1)/quantiles are taken over S at every grid point. Quantiles between stored levels are
         linearly interpolated.
Limits : Day-of-year is normalised to a non-leap calendar (Feb 29 pools with Feb 28). Pooling assumes stationarity
         within the period.
         Gamma-fitting for skewed precipitation is not implemented (empirical quantiles are used).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import xarray as xr

from ml.core.provenance import DataKind, config_hash


class InsufficientSamplesError(ValueError):
    """Raised when too few historical samples fall in the requested period/window."""


@dataclass(frozen=True)
class ClimatologyConfig:
    """Parameters that fully determine a climatology (also recorded in provenance)."""

    variable: str
    period: tuple[int, int]
    target_doy: int
    window_days: int = 7
    min_samples: int = 100
    quantile_step: float = 0.01

    def levels(self) -> np.ndarray:
        n = int(round(1.0 / self.quantile_step))
        return np.round(np.arange(1, n) * self.quantile_step, 6)

    def digest(self) -> str:
        return config_hash(
            {"v": self.variable, "p": self.period, "d": self.target_doy, "w": self.window_days,
             "s": self.quantile_step}
        )


@dataclass
class Climatology:
    """Computed climatology on a lat/lon grid."""

    config: ClimatologyConfig
    mean: np.ndarray
    std: np.ndarray
    levels: np.ndarray
    quantiles: np.ndarray  # (n_levels, lat, lon)
    n_samples: int
    latitudes: np.ndarray
    longitudes: np.ndarray
    data_kind: DataKind
    units: str = ""
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def median(self) -> np.ndarray:
        return self.quantile_at(0.5)

    def quantile_at(self, p: float) -> np.ndarray:
        """Climatological quantile field at probability ``p`` (linear interpolation, clamped to stored levels)."""
        if not 0.0 < p < 1.0:
            raise ValueError("p must lie strictly between 0 and 1")
        lv = self.levels
        if p <= lv[0]:
            return self.quantiles[0]
        if p >= lv[-1]:
            return self.quantiles[-1]
        k = int(np.searchsorted(lv, p, side="right") - 1)
        w = (p - lv[k]) / (lv[k + 1] - lv[k])
        return (1.0 - w) * self.quantiles[k] + w * self.quantiles[k + 1]

    def quantile_stack(self) -> np.ndarray:
        return self.quantiles

    def digest(self) -> str:
        return self.config.digest()


def normalized_dayofyear(time: xr.DataArray) -> xr.DataArray:
    """Day of year on a non-leap calendar (Mar 1 is always 60), so the same date maps to the same number every year."""
    doy = time.dt.dayofyear
    return doy - ((time.dt.is_leap_year) & (doy > 59)).astype(int)


def target_dayofyear(when) -> int:  # noqa: ANN001 - datetime/date/Timestamp
    """Normalised (non-leap) day of year of ``when``; use this to build ``ClimatologyConfig.target_doy``."""
    import pandas as pd

    ts = pd.Timestamp(when)
    doy = ts.dayofyear
    return int(doy - (1 if ts.is_leap_year and doy > 59 else 0))


def _circular_doy_distance(doy: xr.DataArray, target: int) -> xr.DataArray:
    return abs(((doy - target + 182) % 365) - 182)


def build_climatology(
    da: xr.DataArray, config: ClimatologyConfig, data_kind: DataKind = DataKind.REANALYSIS
) -> Climatology:
    """Compute the climatology described by ``config`` from ``da`` (lazy inputs are computed here)."""
    if "time" not in da.dims:
        raise ValueError("Input DataArray must have a 'time' dimension")
    lat_name = "latitude" if "latitude" in da.dims else "lat"
    lon_name = "longitude" if "longitude" in da.dims else "lon"
    years = da["time"].dt.year
    in_period = (years >= config.period[0]) & (years <= config.period[1])
    in_window = _circular_doy_distance(normalized_dayofyear(da["time"]), config.target_doy) <= config.window_days
    sel = da.isel(time=np.flatnonzero((in_period & in_window).values))
    n = int(sel.sizes["time"])
    if n < config.min_samples:
        raise InsufficientSamplesError(
            f"Only {n} samples in period {config.period} within +/-{config.window_days} d of day "
            f"{config.target_doy}; need >= {config.min_samples}"
        )
    sel = sel.chunk({"time": -1}) if sel.chunks is not None else sel
    mean = sel.mean("time", skipna=True).compute()
    std = sel.std("time", ddof=1, skipna=True).compute()
    q = sel.quantile(config.levels(), dim="time", skipna=True).compute()
    return Climatology(
        config=config,
        mean=mean.values.astype(np.float64),
        std=std.values.astype(np.float64),
        levels=config.levels(),
        quantiles=q.transpose("quantile", lat_name, lon_name).values.astype(np.float64),
        n_samples=n,
        latitudes=da[lat_name].values.astype(np.float64),
        longitudes=da[lon_name].values.astype(np.float64),
        data_kind=data_kind,
        units=str(da.attrs.get("units", "")),
    )
