"""Dataset validation. Nothing is silently discarded: every problem becomes a recorded :class:`Finding`.

Checks: missing dimensions/variables, unexpected dimensions, invalid/non-monotonic/duplicate coordinates,
latitude and longitude ranges, unit mismatches, NaN-heavy fields, out-of-range values, duplicate and
irregular timestamps (temporal discontinuity), and grid incompatibility with a reference grid.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum

import numpy as np
import xarray as xr

from ml.core.grid import GridSpec


class Severity(StrEnum):
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


@dataclass(frozen=True)
class Finding:
    severity: Severity
    code: str
    message: str
    variable: str | None = None


@dataclass
class ValidationReport:
    findings: list[Finding] = field(default_factory=list)

    def add(self, severity: Severity, code: str, message: str, variable: str | None = None) -> None:
        self.findings.append(Finding(severity, code, message, variable))

    @property
    def ok(self) -> bool:
        """True when there are no ERROR findings (WARN/INFO do not block ingestion)."""
        return not any(f.severity == Severity.ERROR for f in self.findings)

    def codes(self, severity: Severity | None = None) -> set[str]:
        return {f.code for f in self.findings if severity is None or f.severity == severity}

    def to_dict(self) -> dict:
        return {"ok": self.ok, "findings": [asdict(f) for f in self.findings]}


@dataclass(frozen=True)
class ValidationSchema:
    """Expectations for one dataset type."""

    required_vars: tuple[str, ...] = ()
    required_dims: tuple[str, ...] = ("latitude", "longitude")
    allowed_dims: tuple[str, ...] | None = None
    expected_units: dict[str, str] = field(default_factory=dict)
    valid_ranges: dict[str, tuple[float, float]] = field(default_factory=dict)
    max_nan_fraction: float = 0.2
    warn_nan_fraction: float = 0.05
    reference_grid: GridSpec | None = None
    grid_tolerance_deg: float = 1e-4
    max_gap_factor: float = 1.5


def _check_structure(ds: xr.Dataset, schema: ValidationSchema, rep: ValidationReport) -> None:
    for d in schema.required_dims:
        if d not in ds.dims:
            rep.add(Severity.ERROR, "MISSING_DIMENSION", f"required dimension '{d}' is missing")
    for v in schema.required_vars:
        if v not in ds.data_vars:
            rep.add(Severity.ERROR, "MISSING_VARIABLE", f"required variable '{v}' is missing", v)
    if schema.allowed_dims is not None:
        for d in ds.dims:
            if d not in schema.allowed_dims:
                rep.add(Severity.WARN, "UNEXPECTED_DIMENSION", f"unexpected dimension '{d}'")


def _check_coords(ds: xr.Dataset, rep: ValidationReport) -> None:
    for name, lo, hi in (("latitude", -90.0, 90.0), ("longitude", -180.0, 360.0)):
        if name not in ds.coords:
            continue
        vals = np.asarray(ds[name].values, float)
        if not np.isfinite(vals).all():
            rep.add(Severity.ERROR, "INVALID_COORDINATE", f"{name} contains NaN/inf")
            continue
        if vals.min() < lo or vals.max() > hi:
            code = "INVALID_LATITUDE_RANGE" if name == "latitude" else "INVALID_LONGITUDE_RANGE"
            rep.add(Severity.ERROR, code, f"{name} outside [{lo}, {hi}]: [{vals.min()}, {vals.max()}]")
        if len(np.unique(vals)) != len(vals):
            rep.add(Severity.ERROR, "DUPLICATE_COORDINATE", f"{name} has duplicate values")
        elif vals.size > 1 and not (np.all(np.diff(vals) > 0) or np.all(np.diff(vals) < 0)):
            rep.add(Severity.ERROR, "NON_MONOTONIC_COORDINATE", f"{name} is not monotonic")


def _check_units_and_values(ds: xr.Dataset, schema: ValidationSchema, rep: ValidationReport) -> None:
    for var, expected in schema.expected_units.items():
        if var not in ds.data_vars:
            continue
        actual = ds[var].attrs.get("units")
        if actual is None:
            rep.add(Severity.WARN, "MISSING_UNITS", f"variable '{var}' has no units attribute", var)
        elif str(actual) != expected:
            rep.add(Severity.ERROR, "UNIT_MISMATCH", f"'{var}' has units '{actual}', expected '{expected}'", var)
    for var in ds.data_vars:
        da = ds[var]
        if da.size == 0:
            rep.add(Severity.ERROR, "EMPTY_VARIABLE", f"variable '{var}' has no data", str(var))
            continue
        frac = float(da.isnull().mean().compute()) if da.chunks is not None else float(np.isnan(da.values).mean())
        if frac > schema.max_nan_fraction:
            rep.add(Severity.ERROR, "NAN_HEAVY", f"'{var}' is {frac:.1%} NaN (limit {schema.max_nan_fraction:.0%})", str(var))
        elif frac > schema.warn_nan_fraction:
            rep.add(Severity.WARN, "NAN_ELEVATED", f"'{var}' is {frac:.1%} NaN", str(var))
        rng = schema.valid_ranges.get(str(var))
        if rng is not None:
            bad = float(((da < rng[0]) | (da > rng[1])).mean().compute()) if da.chunks is not None else float(((da.values < rng[0]) | (da.values > rng[1])).mean())
            if bad > 0:
                rep.add(Severity.ERROR if bad > 0.001 else Severity.WARN, "VALUE_OUT_OF_RANGE",
                        f"'{var}': {bad:.3%} of values outside {rng}", str(var))


def _check_time(ds: xr.Dataset, schema: ValidationSchema, rep: ValidationReport) -> None:
    if "time" not in ds.coords or ds["time"].size < 2:
        return
    t = ds["time"].values.astype("datetime64[s]").astype(np.int64)
    if len(np.unique(t)) != len(t):
        rep.add(Severity.ERROR, "DUPLICATE_TIMESTAMPS", "time coordinate contains duplicate timestamps")
        return
    d = np.diff(t)
    if not np.all(d > 0):
        rep.add(Severity.ERROR, "NON_MONOTONIC_TIME", "time coordinate is not strictly increasing")
        return
    step = np.median(d)
    if np.any(d > schema.max_gap_factor * step):
        rep.add(Severity.ERROR, "TEMPORAL_DISCONTINUITY",
                f"gap of {d.max() / 3600:.1f} h exceeds {schema.max_gap_factor}x the typical step {step / 3600:.1f} h")


def _check_grid(ds: xr.Dataset, schema: ValidationSchema, rep: ValidationReport) -> None:
    g = schema.reference_grid
    if g is None or "latitude" not in ds.coords or "longitude" not in ds.coords:
        return
    lat, lon = np.sort(ds["latitude"].values), np.sort(ds["longitude"].values)
    ok = (
        len(lat) == g.nlat and len(lon) == g.nlon
        and np.allclose(lat, g.lats, atol=schema.grid_tolerance_deg)
        and np.allclose(lon, g.lons, atol=schema.grid_tolerance_deg)
    )
    if not ok:
        rep.add(Severity.ERROR, "INCOMPATIBLE_GRID", "grid does not match the reference grid (regrid before combining)")


_ERA5_CDS_NAMES = {
    "t2m": "2m_temperature", "tp": "total_precipitation", "msl": "mean_sea_level_pressure",
    "u10": "10m_u_component_of_wind", "v10": "10m_v_component_of_wind",
}


def check_era5_specific(ds: xr.Dataset, rep: ValidationReport) -> None:
    """ERA5-specific validation: variable naming, UTC time, longitude convention, descending latitude, NaN limits."""
    for var in ds.data_vars:
        if var in _ERA5_CDS_NAMES:
            continue
        if var not in _ERA5_CDS_NAMES.values():
            rep.add(Severity.WARN, "ERA5_NON_STANDARD_VARIABLE",
                    f"'{var}' is not a recognised ERA5 short or CDS long name", var)

    if "time" in ds.coords and ds["time"].size > 0:
        tz = ds["time"].attrs.get("timezone", "")
        if tz and "UTC" not in tz.upper():
            rep.add(Severity.WARN, "ERA5_TIME_NOT_UTC",
                    f"time coordinate timezone is '{tz}', expected UTC")
        t_vals = ds["time"].values.astype("datetime64[s]").astype(np.int64)
        if len(np.unique(t_vals)) != len(t_vals):
            rep.add(Severity.ERROR, "ERA5_DUPLICATE_TIMESTAMPS", "time coordinate contains duplicate timestamps")

    if "longitude" in ds.coords:
        lon = np.asarray(ds["longitude"].values, float)
        if lon.size > 0:
            lo, hi = float(lon.min()), float(lon.max())
            if not (-180 <= lo and hi <= 360):
                rep.add(Severity.WARN, "ERA5_LONGITUDE_RANGE",
                        f"longitude range [{lo}, {hi}] is outside standard conventions [-180, 360]")
            if lo < -180 or hi > 360:
                rep.add(Severity.ERROR, "ERA5_LONGITUDE_EXTREME",
                        f"longitude outside [-180, 360]: [{lo}, {hi}]")

    if "latitude" in ds.coords and ds["latitude"].size > 1:
        lat = np.asarray(ds["latitude"].values, float)
        if not (np.all(np.diff(lat) < 0) or np.all(np.diff(lat) > 0)):
            rep.add(Severity.WARN, "ERA5_LATITUDE_NOT_SORTED", "latitude is not sorted in a single direction")
        elif np.all(np.diff(lat) < 0):
            pass
        else:
            rep.add(Severity.WARN, "ERA5_LATITUDE_ASCENDING",
                    "latitude is ascending; ERA5 typically provides descending (North to South)")

    for var in ds.data_vars:
        da = ds[var]
        if da.size == 0:
            continue
        frac = float(da.isnull().mean().compute()) if da.chunks is not None else float(np.isnan(da.values).mean())
        if frac > 0.5:
            rep.add(Severity.ERROR, "ERA5_NAN_EXPLOSION",
                    f"'{var}' is {frac:.1%} NaN (>50% missing)", var)


def run_validation(ds: xr.Dataset, schema: ValidationSchema, source: str = "") -> ValidationReport:
    """Run all checks and return the report (never raises for data problems)."""
    rep = ValidationReport()
    _check_structure(ds, schema, rep)
    _check_coords(ds, rep)
    _check_units_and_values(ds, schema, rep)
    _check_time(ds, schema, rep)
    _check_grid(ds, schema, rep)
    if source.lower() == "era5":
        check_era5_specific(ds, rep)
    if rep.ok and not rep.findings:
        rep.add(Severity.INFO, "ALL_CHECKS_PASSED", "no problems found")
    return rep
