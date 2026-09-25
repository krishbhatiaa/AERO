"""Synthetic weather-event engine.

Produces a *physically inspired but explicitly synthetic* landfalling-cyclone scenario:

* pressure  : Holland (1980) parametric profile
* wind      : gradient-wind balance for the Holland profile, plus a constant surface inflow angle
* rainfall  : eyewall ring + spiral bands + storm-motion asymmetry + orographic enhancement (all
              invented for demonstration - NOT derived from any dataset)
* truth     : evaluated on a fine grid with sub-grid lognormal convective variability
* forecast  : conservative block-mean of the truth on the coarse grid (so coarse == aggregated fine)
* ensemble  : perturbed storm track / intensity / size, evaluated directly on the coarse grid
* climate   : gamma-distributed wet-day sample used to build a *synthetic* climatology

Everything here carries ``DataKind.SYNTHETIC_DEMO``. Outputs must never be shown as observations.

References
----------
Holland, G. J. (1980) An analytic model of the wind and pressure profiles in hurricanes.
Mon. Wea. Rev. 108, 1212-1218.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import xarray as xr
from scipy import ndimage

from ml.core.geometry import bearing_deg, from_local_xy, haversine_km, to_local_xy
from ml.core.grid import GridSpec, block_mean
from ml.core.provenance import DataKind
from ml.data.landmask import land_mask

OMEGA = 7.2921e-5  # Earth's rotation rate, rad s-1
RHO_AIR = 1.15  # kg m-3, near-surface tropical air density (assumption)
P_ENV = 101000.0  # Pa, ambient pressure (assumption)


@dataclass(frozen=True)
class ScenarioConfig:
    """All knobs of the synthetic scenario (deterministic for a given seed)."""

    seed: int = 7
    init_time: datetime = datetime(2000, 9, 1, tzinfo=UTC)
    lead_hours: tuple[int, ...] = (0, 6, 12, 18, 24, 30, 36, 42, 48)
    coarse_grid: GridSpec = GridSpec(12.05, 80.05, 0.1, 0.1, 120, 120)
    refine: int = 2
    n_members: int = 10
    n_climate_years: int = 30
    climate_window_days: int = 7
    start: tuple[float, float] = (15.2, 88.4)  # storm centre at T+0 (lat, lon)
    landfall: tuple[float, float] = (20.6, 86.9)  # storm centre at landfall (lat, lon)
    landfall_lead_h: int = 36
    curvature_deg: float = 0.5  # eastward bulge of the track (degrees longitude)
    vmax_start_ms: float = 24.0
    vmax_peak_ms: float = 45.0
    decay_per_h: float = 0.095  # exponential filling rate after landfall
    rmax_km: float = 32.0
    holland_b: float = 1.3
    peak_rain_mmph: float = 14.0
    boundary_path: Path | None = None

    @property
    def fine_grid(self) -> GridSpec:
        return self.coarse_grid.refined(self.refine)


@dataclass(frozen=True)
class StormState:
    """Instantaneous parameters of the synthetic vortex."""

    lat: float
    lon: float
    vmax_ms: float
    rmax_km: float
    motion_bearing_deg: float
    motion_speed_kmh: float

    @property
    def pressure_deficit_pa(self) -> float:
        return float(RHO_AIR * np.e * self.vmax_ms**2 / 1.3)


def _centre(h: float, cfg: ScenarioConfig) -> tuple[float, float]:
    lat0, lon0 = cfg.start
    latl, lonl = cfg.landfall
    lf = cfg.landfall_lead_h
    if h <= lf:
        s = h / lf
        return lat0 + (latl - lat0) * s, lon0 + (lonl - lon0) * s + cfg.curvature_deg * float(np.sin(np.pi * s))
    slow = 0.6  # storms slow down after landfall
    after = h - lf
    return latl + (latl - lat0) / lf * slow * after, lonl + (lonl - lon0) / lf * slow * after


def storm_state(h: float, cfg: ScenarioConfig) -> StormState:
    """Ground-truth storm parameters at lead time ``h`` hours."""
    lat, lon = _centre(h, cfg)
    lat_b, lon_b = _centre(h - 1.0, cfg)
    lat_f, lon_f = _centre(h + 1.0, cfg)
    speed = float(haversine_km(lat_b, lon_b, lat_f, lon_f)) / 2.0
    bearing = float(bearing_deg(lat_b, lon_b, lat_f, lon_f))
    lf = cfg.landfall_lead_h
    if h <= lf:
        vmax = cfg.vmax_start_ms + (cfg.vmax_peak_ms - cfg.vmax_start_ms) * float(np.sin(0.5 * np.pi * h / lf))
    else:
        vmax = cfg.vmax_peak_ms * float(np.exp(-cfg.decay_per_h * (h - lf)))
    return StormState(lat, lon, vmax, cfg.rmax_km * (1.0 + 0.004 * h), bearing, speed)


def synthetic_elevation(grid: GridSpec, land: np.ndarray, seed: int) -> np.ndarray:
    """Fictional terrain (m): a Gaussian ridge loosely placed like an inland range plus smooth noise."""
    lon2d, lat2d = np.meshgrid(grid.lons, grid.lats)
    p0, p1 = np.array([82.0, 17.0]), np.array([85.2, 22.6])
    d = p1 - p0
    t = np.clip(((lon2d - p0[0]) * d[0] + (lat2d - p0[1]) * d[1]) / float(d @ d), 0.0, 1.0)
    dist = np.hypot(lon2d - (p0[0] + t * d[0]), lat2d - (p0[1] + t * d[1]))
    ridge = 900.0 * np.exp(-((dist / 0.7) ** 2))
    noise = ndimage.gaussian_filter(np.random.default_rng(seed).standard_normal(grid.shape), 6.0)
    noise = noise / (noise.std() + 1e-12)
    return np.clip(ridge + 120.0 * noise, 0.0, None) * (land > 0.5)


def evaluate_storm(
    lat2d: np.ndarray, lon2d: np.ndarray, st: StormState, elevation: np.ndarray, land: np.ndarray,
    cfg: ScenarioConfig,
) -> dict[str, np.ndarray]:
    """Evaluate the analytic vortex on any grid. Returns ``tp`` (mm/6h), ``msl`` (Pa), ``u10``, ``v10`` (m/s)."""
    x, y = to_local_xy(lat2d, lon2d, st.lat, st.lon)
    r_km = np.hypot(x, y)
    r_safe = np.maximum(r_km, 1.0)
    r_m, rm_m = r_safe * 1000.0, st.rmax_km * 1000.0
    b, dp = cfg.holland_b, st.pressure_deficit_pa
    ratio = (rm_m / r_m) ** b
    msl = P_ENV - dp * (1.0 - np.exp(-ratio))

    f = 2.0 * OMEGA * np.sin(np.radians(lat2d))
    vg = np.sqrt((b * dp / RHO_AIR) * ratio * np.exp(-ratio) + (r_m * f / 2.0) ** 2) - r_m * f / 2.0
    tx, ty = -y / r_safe, x / r_safe  # cyclonic (counter-clockwise, northern hemisphere)
    rx, ry = x / r_safe, y / r_safe
    alpha = np.radians(20.0)  # surface inflow angle (assumption)
    surface = 0.8 * (1.0 - 0.25 * land)
    u10 = surface * vg * (np.cos(alpha) * tx - np.sin(alpha) * rx)
    v10 = surface * vg * (np.cos(alpha) * ty - np.sin(alpha) * ry)

    rr = r_km / st.rmax_km
    theta = np.arctan2(y, x)
    theta_m = np.radians(90.0 - st.motion_bearing_deg)
    eye = np.exp(-(((rr - 1.1) / 0.6) ** 2))
    outer = 0.12 * np.exp(-rr / 4.0) * (1.0 - np.exp(-(rr**2)))
    bands = 0.22 * (0.5 + 0.5 * np.cos(2.0 * (theta - 1.4 * np.log1p(rr)))) ** 2 * np.exp(-(((rr - 3.5) / 2.5) ** 2))
    asym = 1.0 + 0.35 * np.cos(theta - theta_m - np.pi / 4.0)
    intensity = max((st.vmax_ms / cfg.vmax_peak_ms) ** 1.5, 0.05)
    rate = cfg.peak_rain_mmph * intensity * (eye + outer + bands) * asym
    oro = 1.0 + 0.8 * np.clip(elevation / 800.0, 0.0, 1.2)
    return {"tp": rate * 6.0 * oro, "msl": msl, "u10": u10, "v10": v10}


def _lognormal_cells(shape: tuple[int, int], rng: np.random.Generator, sigma: float = 0.45) -> np.ndarray:
    g = ndimage.gaussian_filter(rng.standard_normal(shape), 1.5)
    g = np.clip(g / (g.std() + 1e-12), -2.5, 2.5)
    return np.exp(sigma * g - 0.5 * sigma**2)


@dataclass
class SyntheticScenario:
    """Container for every array of the synthetic demo scenario. ``data_kind`` is always SYNTHETIC_DEMO."""

    config: ScenarioConfig
    coarse_grid: GridSpec
    fine_grid: GridSpec
    lead_hours: list[int]
    valid_times: list[datetime]
    truth_fine: dict[str, np.ndarray]
    forecast_coarse: dict[str, np.ndarray]
    ensemble_coarse: dict[str, np.ndarray]
    truth_storms: list[StormState]
    member_storms: list[list[StormState]]
    elevation_fine: np.ndarray
    land_fine: np.ndarray
    elevation_coarse: np.ndarray
    land_coarse: np.ndarray
    climate: xr.DataArray
    geography_source: str
    data_kind: DataKind = DataKind.SYNTHETIC_DEMO

    def forecast_dataset(self) -> xr.Dataset:
        """Coarse control forecast as a canonical xarray Dataset (time, lat, lon)."""
        return _to_dataset(self.forecast_coarse, self.coarse_grid, self.valid_times, "SYNTHETIC coarse control forecast")

    def truth_dataset(self) -> xr.Dataset:
        """Fine-grid synthetic truth as a canonical xarray Dataset (time, lat, lon)."""
        return _to_dataset(self.truth_fine, self.fine_grid, self.valid_times, "SYNTHETIC fine-grid truth")


_UNITS = {"tp": "mm", "msl": "Pa", "u10": "m s-1", "v10": "m s-1"}


def _to_dataset(fields: dict[str, np.ndarray], grid: GridSpec, times: list[datetime], title: str) -> xr.Dataset:
    ds = xr.Dataset(
        {
            name: (("time", "latitude", "longitude"), arr.astype(np.float32), {"units": _UNITS[name]})
            for name, arr in fields.items()
        },
        coords={
            "time": np.array([np.datetime64(t.replace(tzinfo=None), "ns") for t in times]),
            "latitude": ("latitude", grid.lats, {"units": "degrees_north"}),
            "longitude": ("longitude", grid.lons, {"units": "degrees_east"}),
        },
        attrs={"title": title, "data_kind": DataKind.SYNTHETIC_DEMO.value, "synthetic": 1},
    )
    ds["tp"].attrs["accumulation_hours"] = 6
    return ds


def synthetic_climate(
    grid: GridSpec, land: np.ndarray, elevation: np.ndarray, cfg: ScenarioConfig
) -> xr.DataArray:
    """Synthetic 'historical' precipitation sample (mm/6h) around the scenario's day of year.

    One 12Z-labelled sample per day for ``n_climate_years`` years and +/- ``climate_window_days`` days.
    Gamma-distributed wet amounts with land/orography-dependent scale; wet-occurrence probability 0.3.
    Invented for demonstration - it is NOT a real climatology.
    """
    rng = np.random.default_rng(cfg.seed + 1000)
    years = range(1991, 1991 + cfg.n_climate_years)
    offsets = range(-cfg.climate_window_days, cfg.climate_window_days + 1)
    month, day = cfg.init_time.month, min(cfg.init_time.day, 28) if cfg.init_time.month == 2 else cfg.init_time.day
    times = [datetime(y, month, day, 12, tzinfo=UTC) + timedelta(days=o) for y in years for o in offsets]
    scale = 5.0 * (1.0 + 0.6 * land) * (1.0 + 0.8 * np.clip(elevation / 800.0, 0.0, 1.2))
    shape = (len(times), *grid.shape)
    wet = rng.random(shape, dtype=np.float32) < 0.3
    amount = rng.standard_gamma(0.7, size=shape, dtype=np.float32) * scale.astype(np.float32)
    tp = np.where(wet, amount, np.float32(0.0)).astype(np.float32)
    return xr.DataArray(
        tp,
        dims=("time", "latitude", "longitude"),
        coords={
            "time": np.array([np.datetime64(t.replace(tzinfo=None), "ns") for t in times]),
            "latitude": grid.lats,
            "longitude": grid.lons,
        },
        name="tp",
        attrs={"units": "mm", "accumulation_hours": 6, "data_kind": DataKind.SYNTHETIC_DEMO.value,
               "title": "SYNTHETIC climatological sample"},
    )


def _perturbed(st: StormState, h: float, z: np.ndarray) -> StormState:
    sigma_km = 15.0 + 1.8 * h
    lat, lon = from_local_xy(z[0] * sigma_km, z[1] * sigma_km, st.lat, st.lon)
    return replace(
        st, lat=float(lat), lon=float(lon),
        vmax_ms=float(max(st.vmax_ms * (1.0 + z[2] * (0.05 + 0.0012 * h)), 5.0)),
        rmax_km=float(max(st.rmax_km * (1.0 + 0.08 * z[3]), 10.0)),
    )


def generate_scenario(cfg: ScenarioConfig | None = None) -> SyntheticScenario:
    """Build the full deterministic synthetic scenario for ``cfg`` (default: the demo scenario)."""
    cfg = cfg or ScenarioConfig()
    cg, fg = cfg.coarse_grid, cfg.fine_grid
    land_f, geography = land_mask(fg, cfg.boundary_path)
    land_c = block_mean(land_f, cfg.refine)
    elev_f = synthetic_elevation(fg, land_f, cfg.seed)
    elev_c = block_mean(elev_f, cfg.refine)

    lon_f, lat_f = np.meshgrid(fg.lons, fg.lats)
    lon_c, lat_c = np.meshgrid(cg.lons, cg.lats)
    leads = list(cfg.lead_hours)
    storms = [storm_state(float(h), cfg) for h in leads]

    truth: dict[str, list[np.ndarray]] = {k: [] for k in _UNITS}
    for i, st in enumerate(storms):
        fields = evaluate_storm(lat_f, lon_f, st, elev_f, land_f, cfg)
        fields["tp"] = fields["tp"] * _lognormal_cells(fg.shape, np.random.default_rng(cfg.seed * 10_000 + i))
        for k, v in fields.items():
            truth[k].append(v)
    truth_fine = {k: np.stack(v).astype(np.float32) for k, v in truth.items()}
    forecast = {k: block_mean(v, cfg.refine).astype(np.float32) for k, v in truth_fine.items()}

    rng = np.random.default_rng(cfg.seed + 500)
    member_states: list[list[StormState]] = []
    members: list[np.ndarray] = []
    for _ in range(cfg.n_members):
        z = rng.standard_normal(4)
        states = [_perturbed(st, float(h), z) for st, h in zip(storms, leads, strict=True)]
        member_states.append(states)
        members.append(np.stack([evaluate_storm(lat_c, lon_c, s, elev_c, land_c, cfg)["tp"] for s in states]))
    ensemble = {"tp": np.stack(members).astype(np.float32)}

    return SyntheticScenario(
        config=cfg, coarse_grid=cg, fine_grid=fg, lead_hours=leads,
        valid_times=[cfg.init_time + timedelta(hours=h) for h in leads],
        truth_fine=truth_fine, forecast_coarse=forecast, ensemble_coarse=ensemble,
        truth_storms=storms, member_storms=member_states,
        elevation_fine=elev_f.astype(np.float32), land_fine=land_f.astype(np.float32),
        elevation_coarse=elev_c.astype(np.float32), land_coarse=land_c.astype(np.float32),
        climate=synthetic_climate(cg, land_c, elev_c, cfg), geography_source=geography,
    )
