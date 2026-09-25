"""Canonicalisation: rename to canonical names, convert units, normalise coordinates, record what was done."""
from __future__ import annotations

import json

import numpy as np
import xarray as xr

from ml.core.config import load_config
from ml.core.geometry import normalize_lon
from ml.core.provenance import config_hash
from ml.core.units import convert

_DIM_ALIASES = {"lat": "latitude", "lon": "longitude", "valid_time": "time", "Latitude": "latitude", "Longitude": "longitude"}


def canonicalize(ds: xr.Dataset, variable_map: dict[str, dict[str, str]], lon_convention: str = "-180_180") -> xr.Dataset:
    """Return a canonical copy of ``ds`` (lazy) and record every transformation in ``attrs['preprocess_log']``.

    * dimension/coordinate aliases -> latitude / longitude / time
    * source variable -> canonical variable via ``variable_map`` (with unit conversion to config/variables.yaml units)
    * longitude wrapped to ``lon_convention`` and sorted; latitude sorted ascending
    """
    log: list[str] = []
    renames = {k: v for k, v in _DIM_ALIASES.items() if k in ds.variables or k in ds.dims}
    if renames:
        ds = ds.rename(renames)
        log.append(f"renamed coords: {renames}")
    canon = load_config("variables")["variables"]
    out = xr.Dataset(attrs=dict(ds.attrs))
    for src, spec in variable_map.items():
        if src not in ds.data_vars:
            continue
        name = spec["canonical"]
        target_units = canon[name]["units"]
        from_units = spec.get("from_units", ds[src].attrs.get("units", target_units))
        da = ds[src]
        if from_units != target_units:
            da = xr.apply_ufunc(lambda x, f=from_units, t=target_units: convert(x, f, t), da, dask="parallelized", output_dtypes=[np.float64])
            log.append(f"{src}: {from_units} -> {target_units}")
        out[name] = da.assign_attrs(units=target_units, source_variable=src)
    if not out.data_vars:
        raise ValueError("canonicalize: none of the mapped source variables are present in the dataset")
    lon_name = "longitude"
    if lon_name in out.coords:
        out = out.assign_coords({lon_name: normalize_lon(out[lon_name].values, lon_convention)}).sortby(lon_name)
        log.append(f"longitude wrapped to {lon_convention}")
    if "latitude" in out.coords:
        out = out.sortby("latitude")
    out.attrs["preprocess_log"] = json.dumps(log)
    out.attrs["preprocess_config_hash"] = config_hash({"map": variable_map, "lon": lon_convention, "log": log})
    return out
