import numpy as np
import pandas as pd
import xarray as xr

from data_pipeline.validation.checks import Severity, ValidationSchema, run_validation
from ml.core.grid import GridSpec


def make(nt=6, ny=5, nx=6, units="mm", start="2000-01-01", freq="6h"):
    times = pd.date_range(start, periods=nt, freq=freq)
    rng = np.random.default_rng(0)
    return xr.Dataset(
        {"tp": (("time", "latitude", "longitude"), rng.random((nt, ny, nx)) * 10, {"units": units})},
        coords={"time": times, "latitude": np.linspace(10, 20, ny), "longitude": np.linspace(80, 90, nx)},
    )


SCHEMA = ValidationSchema(required_vars=("tp",), expected_units={"tp": "mm"}, valid_ranges={"tp": (0.0, 2000.0)})


def codes(ds, schema=SCHEMA, severity=Severity.ERROR):
    return run_validation(ds, schema).codes(severity)


def test_clean_dataset_passes_with_info_finding():
    rep = run_validation(make(), SCHEMA)
    assert rep.ok and rep.codes() == {"ALL_CHECKS_PASSED"}


def test_missing_variable_and_dimension():
    assert "MISSING_VARIABLE" in codes(make().drop_vars("tp").assign(x=xr.DataArray(1.0)))
    ds = make().isel(time=0, drop=True)
    assert "MISSING_DIMENSION" not in codes(ds)  # time is not a required dim by default
    assert "MISSING_DIMENSION" in codes(ds, ValidationSchema(required_dims=("time", "latitude", "longitude")))


def test_unexpected_dimension_is_a_warning():
    s = ValidationSchema(required_vars=("tp",), allowed_dims=("time", "latitude", "longitude"))
    ds = make().expand_dims(member=2)
    assert "UNEXPECTED_DIMENSION" in codes(ds, s, Severity.WARN)


def test_invalid_coordinates():
    assert "INVALID_LATITUDE_RANGE" in codes(make().assign_coords(latitude=np.linspace(50, 120, 5)))
    assert "INVALID_LONGITUDE_RANGE" in codes(make().assign_coords(longitude=np.linspace(80, 400, 6)))
    assert "DUPLICATE_COORDINATE" in codes(make().assign_coords(latitude=[10, 10, 12, 14, 16]))
    assert "NON_MONOTONIC_COORDINATE" in codes(make().assign_coords(latitude=[10, 15, 12, 14, 16]))
    bad = make().assign_coords(latitude=[10, np.nan, 12, 14, 16])
    assert "INVALID_COORDINATE" in codes(bad)


def test_unit_problems():
    assert "UNIT_MISMATCH" in codes(make(units="m"))
    ds = make()
    del ds["tp"].attrs["units"]
    assert "MISSING_UNITS" in codes(ds, severity=Severity.WARN)


def test_nan_heavy_and_elevated_fields():
    ds = make()
    v = ds["tp"].values.copy()
    v[:, :3, :] = np.nan
    assert "NAN_HEAVY" in codes(ds.assign(tp=(ds["tp"].dims, v, {"units": "mm"})))
    v2 = ds["tp"].values.copy()
    v2.ravel()[:12] = np.nan  # 12/180 = 6.7 % (> 5 % warning, < 20 % error)
    assert "NAN_ELEVATED" in codes(ds.assign(tp=(ds["tp"].dims, v2, {"units": "mm"})), severity=Severity.WARN)


def test_value_range_and_empty_variable():
    ds = make(ny=20, nx=20)  # 2400 values: one bad value is 0.04 % (warning, below the 0.1 % error limit)
    v = ds["tp"].values.copy()
    v[0, 0, 0] = 99999.0
    assert "VALUE_OUT_OF_RANGE" in codes(ds.assign(tp=(ds["tp"].dims, v, {"units": "mm"})), severity=Severity.WARN)
    v[:8, 0, 0] = 99999.0  # >0.1 % of values -> error
    assert "VALUE_OUT_OF_RANGE" in codes(ds.assign(tp=(ds["tp"].dims, v, {"units": "mm"})))
    v[:] = -5.0
    assert "VALUE_OUT_OF_RANGE" in codes(ds.assign(tp=(ds["tp"].dims, v, {"units": "mm"})))
    assert "EMPTY_VARIABLE" in codes(make().isel(time=slice(0, 0)))


def test_duplicate_timestamps_non_monotonic_and_gaps():
    t = pd.date_range("2000-01-01", periods=6, freq="6h").to_list()
    t[3] = t[2]
    assert "DUPLICATE_TIMESTAMPS" in codes(make().assign_coords(time=t))
    t2 = pd.date_range("2000-01-01", periods=6, freq="6h").to_list()
    t2[2], t2[3] = t2[3], t2[2]
    assert "NON_MONOTONIC_TIME" in codes(make().assign_coords(time=t2))
    t3 = pd.date_range("2000-01-01", periods=6, freq="6h").to_list()
    t3[4:] = [x + pd.Timedelta(days=2) for x in t3[4:]]
    assert "TEMPORAL_DISCONTINUITY" in codes(make().assign_coords(time=t3))


def test_incompatible_grid():
    g = GridSpec(10.0, 80.0, 2.5, 2.0, 5, 6)
    s = ValidationSchema(required_vars=("tp",), reference_grid=g)
    assert "INCOMPATIBLE_GRID" not in codes(make(), s)
    assert "INCOMPATIBLE_GRID" in codes(make(ny=4), s)
    assert "INCOMPATIBLE_GRID" in codes(make().assign_coords(latitude=np.linspace(10.5, 20.5, 5)), s)


def test_report_serialises_and_never_hides_errors():
    rep = run_validation(make(units="m"), SCHEMA)
    d = rep.to_dict()
    assert d["ok"] is False and any(f["code"] == "UNIT_MISMATCH" for f in d["findings"])
