"""Generate sample ERA5 NetCDF reanalysis file for real data mode ingestion.

Creates var/data/raw/era5/era5_sample_event.nc with realistic extreme weather
anomaly signals over the Indian region (Bay of Bengal / Odisha coast).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import xarray as xr

ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT_DIR / "var" / "data" / "raw" / "era5"


def generate_era5_sample() -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_file = OUTPUT_DIR / "era5_sample_event.nc"

    lats = np.linspace(5.0, 30.0, 101)   # 0.25 deg grid
    lons = np.linspace(68.0, 98.0, 121)
    n_times = 9                          # 9 time steps (e.g. 6-hourly over 48h)
    start_time = datetime(2021, 5, 15, 0, 0)
    times = [start_time + timedelta(hours=6 * i) for i in range(n_times)]

    n_lat = len(lats)
    n_lon = len(lons)

    # Base grid mesh
    lat_mesh, lon_mesh = np.meshgrid(lats, lons, indexing="ij")

    # Generate synthetic cyclone track moving from SE to NW across Bay of Bengal
    tp_data = np.zeros((n_times, n_lat, n_lon), dtype=np.float32)
    msl_data = np.full((n_times, n_lat, n_lon), 101325.0, dtype=np.float32)
    t2m_data = np.full((n_times, n_lat, n_lon), 298.15, dtype=np.float32)
    u10_data = np.random.randn(n_times, n_lat, n_lon).astype(np.float32) * 2.0
    v10_data = np.random.randn(n_times, n_lat, n_lon).astype(np.float32) * 2.0

    center_lat = 14.0
    center_lon = 88.0

    for t_idx in range(n_times):
        c_lat = center_lat + t_idx * 1.2
        c_lon = center_lon - t_idx * 1.0

        dist_sq = (lat_mesh - c_lat) ** 2 + (lon_mesh - c_lon) ** 2

        # Rain shield (total precipitation in meters/6h)
        rain = 0.08 * np.exp(-dist_sq / 4.0)
        tp_data[t_idx] += rain.astype(np.float32)

        # Pressure drop at cyclone core (Pa)
        p_drop = 3500.0 * np.exp(-dist_sq / 6.0)
        msl_data[t_idx] -= p_drop.astype(np.float32)

        # Strong cyclonic winds
        r = np.sqrt(dist_sq) + 0.01
        u10_data[t_idx] += (- (lat_mesh - c_lat) / r * 25.0 * np.exp(-dist_sq / 5.0)).astype(np.float32)
        v10_data[t_idx] += ((lon_mesh - c_lon) / r * 25.0 * np.exp(-dist_sq / 5.0)).astype(np.float32)

    ds = xr.Dataset(
        data_vars={
            "tp": (("valid_time", "latitude", "longitude"), tp_data, {"units": "m", "long_name": "Total precipitation"}),
            "msl": (("valid_time", "latitude", "longitude"), msl_data, {"units": "Pa", "long_name": "Mean sea level pressure"}),
            "t2m": (("valid_time", "latitude", "longitude"), t2m_data, {"units": "K", "long_name": "2m temperature"}),
            "u10": (("valid_time", "latitude", "longitude"), u10_data, {"units": "m s**-1", "long_name": "10m u-component of wind"}),
            "v10": (("valid_time", "latitude", "longitude"), v10_data, {"units": "m s**-1", "long_name": "10m v-component of wind"}),
        },
        coords={
            "valid_time": times,
            "latitude": lats,
            "longitude": lons,
        },
        attrs={
            "title": "ERA5 Reanalysis Sample Event",
            "source": "ECMWF ERA5 Reanalysis Data",
            "institution": "NCMRWF / MoES Extreme Weather AI Project",
        }
    )

    ds.to_netcdf(out_file, engine="netcdf4")
    print(f"Generated sample ERA5 NetCDF reanalysis file at: {out_file}")
    return out_file


if __name__ == "__main__":
    generate_era5_sample()
