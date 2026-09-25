import json
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from data_pipeline.adapters.base import AccessStatus, AdapterError, DatasetRequest
from data_pipeline.adapters.registry import all_descriptors, resolve_source
from data_pipeline.adapters.sources import ERA5Adapter, IMDAAAdapter, NEPSAdapter, SyntheticAdapter
from data_pipeline.ingestion.pipeline import JobStatus, run_ingestion
from data_pipeline.storage.local import LocalStorageProvider
from data_pipeline.transformation.canonicalize import canonicalize
from data_pipeline.validation.checks import ValidationSchema
from ml.core.provenance import DataKind

ERA5_MAP = {"tp": {"canonical": "tp", "from_units": "m"}, "msl": {"canonical": "msl", "from_units": "Pa"}}


def era5_like(path=None, lon0=True):
    times = pd.date_range("2020-05-01", periods=4, freq="6h")
    lon = np.arange(0.0, 360.0, 60.0) if lon0 else np.arange(-180.0, 180.0, 60.0)
    ds = xr.Dataset(
        {"tp": (("valid_time", "lat", "lon"), np.full((4, 3, 6), 0.012), {"units": "m"}),
         "msl": (("valid_time", "lat", "lon"), np.full((4, 3, 6), 101000.0), {"units": "Pa"})},
        coords={"valid_time": times, "lat": [30.0, 20.0, 10.0], "lon": lon},
    )
    if path:
        ds.to_netcdf(path)
    return ds


def test_canonicalize_converts_units_wraps_longitude_sorts_and_logs():
    out = canonicalize(era5_like(), ERA5_MAP)
    assert set(out.data_vars) == {"tp", "msl"}
    assert float(out["tp"].isel(time=0, latitude=0, longitude=0)) == pytest.approx(12.0)
    assert out["tp"].attrs["units"] == "mm"
    assert out.latitude.values.tolist() == [10.0, 20.0, 30.0]
    assert out.longitude.values.min() >= -180 and out.longitude.values.max() < 180
    assert list(out.longitude.values) == sorted(out.longitude.values)
    assert "m -> mm" in out.attrs["preprocess_log"] and out.attrs["preprocess_config_hash"]
    with pytest.raises(ValueError):
        canonicalize(era5_like(), {"nope": {"canonical": "tp"}})


def test_restricted_sources_report_status_instead_of_pretending(tmp_path):
    d = {x.name: x for x in all_descriptors(tmp_path)}
    for name in ("IMDAA", "NEPS-G", "NCUM", "IMD"):
        assert d[name].status == AccessStatus.NOT_CONFIGURED  # mapping intentionally empty
    assert d["ERA5"].status in (AccessStatus.ACCESS_REQUIRED, AccessStatus.DOWNLOADABLE)
    assert d["SYNTHETIC"].status == AccessStatus.AVAILABLE and d["SYNTHETIC"].data_kind == DataKind.SYNTHETIC_DEMO
    with pytest.raises(AdapterError):
        NEPSAdapter(tmp_path).open(DatasetRequest())


def test_resolve_source_never_silently_substitutes(tmp_path, monkeypatch):
    monkeypatch.delenv("CDSAPI_KEY", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    r = resolve_source("neps", fallback="era5", data_root=tmp_path)
    assert r.substituted and r.requested == "NEPS-G"
    assert "NOT CONFIGURED" in r.message and r.used == "SYNTHETIC" and "SYNTHETIC / DEMO DATA" in r.message
    (tmp_path / "raw" / "era5").mkdir(parents=True)
    era5_like(tmp_path / "raw" / "era5" / "a.nc")
    r2 = resolve_source("neps", fallback="era5", data_root=tmp_path)
    assert r2.used == "ERA5" and "Using ERA5 development dataset" in r2.message
    assert resolve_source("synthetic").substituted is False
    with pytest.raises(ValueError):
        resolve_source("bogus")


def test_era5_request_is_deterministic_and_validated():
    req = DatasetRequest(("tp", "msl"), datetime(2021, 5, 15, tzinfo=UTC), datetime(2021, 5, 17, tzinfo=UTC), (70.0, 5.0, 98.0, 26.0))
    body = ERA5Adapter.build_request(req)
    assert body["variable"] == ["total_precipitation", "mean_sea_level_pressure"]
    assert body["day"] == ["15", "16", "17"] and body["month"] == ["05"] and body["year"] == ["2021"]
    assert body["area"] == [26.0, 70.0, 5.0, 98.0]
    assert body["data_format"] == "netcdf" and len(body["time"]) == 24
    assert ERA5Adapter.build_request(req) == body
    with pytest.raises(AdapterError):
        ERA5Adapter.build_request(DatasetRequest(("bogus",), req.start, req.end))
    with pytest.raises(AdapterError):
        ERA5Adapter.build_request(DatasetRequest())


def test_local_adapter_reads_netcdf_and_reports_available(tmp_path):
    (tmp_path / "raw" / "era5").mkdir(parents=True)
    era5_like(tmp_path / "raw" / "era5" / "a.nc")
    a = ERA5Adapter(tmp_path)
    assert a.descriptor().status == AccessStatus.AVAILABLE
    ds = a.open(DatasetRequest(("tp",)))
    assert list(ds.data_vars) == ["tp"]


def test_ingestion_success_records_everything_and_writes_zarr(tmp_path):
    (tmp_path / "raw" / "era5").mkdir(parents=True)
    era5_like(tmp_path / "raw" / "era5" / "a.nc")
    store = LocalStorageProvider(tmp_path / "store")
    schema = ValidationSchema(required_vars=("tp", "msl"), expected_units={"tp": "m", "msl": "Pa"}, valid_ranges={"tp": (0, 5), "msl": (80000, 110000)})
    job = run_ingestion(ERA5Adapter(tmp_path), DatasetRequest(), store, schema, "era5-test", job_id="job1")
    assert job.status == JobStatus.SUCCEEDED, job.error
    assert job.files[0]["name"] == "a.nc" and len(job.files[0]["sha256"]) == 64 and job.checksum
    assert job.dimensions == {"valid_time": 4, "lat": 3, "lon": 6} and set(job.variables) == {"tp", "msl"}
    assert job.units["tp"] == "m" and job.geographic_extent["north"] == 30.0 and job.temporal_extent["start"].startswith("2020-05-01")
    assert all(s.status == "SUCCEEDED" for s in job.steps) and job.data_kind == "REANALYSIS"
    rec = json.loads(store.get_bytes("jobs/job1.json"))
    assert rec["status"] == "SUCCEEDED" and rec["storage_key"] == job.storage_key
    target, _ = store.zarr_target(job.storage_key)
    back = xr.open_zarr(target, consolidated=False)
    assert float(back["tp"].max()) == pytest.approx(12.0) and back.attrs["data_kind"] == "REANALYSIS"


def test_ingestion_quarantines_failed_validation_and_never_deletes(tmp_path):
    (tmp_path / "raw" / "era5").mkdir(parents=True)
    bad = era5_like().assign_coords(lat=[300.0, 20.0, 10.0])
    bad.to_netcdf(tmp_path / "raw" / "era5" / "bad.nc")
    store = LocalStorageProvider(tmp_path / "store")
    job = run_ingestion(ERA5Adapter(tmp_path), DatasetRequest(), store, ValidationSchema(required_vars=("tp",)), "bad", job_id="job2")
    assert job.status == JobStatus.FAILED and "validation failed" in job.error
    assert any(f["code"] == "INVALID_LATITUDE_RANGE" for f in job.validation["findings"])
    assert store.exists("quarantine/job2.json") and (tmp_path / "raw" / "era5" / "bad.nc").exists()
    assert not store.exists("jobs/job2.json") and job.storage_key is None


def test_ingestion_reports_corrupted_file_and_missing_files(tmp_path):
    (tmp_path / "raw" / "era5").mkdir(parents=True)
    (tmp_path / "raw" / "era5" / "broken.nc").write_bytes(b"this is not a netcdf file")
    store = LocalStorageProvider(tmp_path / "store")
    job = run_ingestion(ERA5Adapter(tmp_path), DatasetRequest(), store, ValidationSchema(), "broken", job_id="job3")
    assert job.status == JobStatus.FAILED and "could not be read" in job.error
    empty = run_ingestion(NEPSAdapter(tmp_path / "none"), DatasetRequest(), store, ValidationSchema(), "none", job_id="job4")
    assert empty.status == JobStatus.FAILED and store.exists("quarantine/job4.json")


def test_synthetic_ingestion_is_labelled_and_fingerprinted(tmp_path):
    store = LocalStorageProvider(tmp_path)
    schema = ValidationSchema(required_vars=("tp",), expected_units={"tp": "mm"}, valid_ranges={"tp": (0, 2000)})
    job = run_ingestion(SyntheticAdapter(), DatasetRequest(("tp",)), store, schema, "syn", job_id="job5")
    assert job.status == JobStatus.SUCCEEDED and job.data_kind == "SYNTHETIC_DEMO" and len(job.checksum) == 64
    a = run_ingestion(SyntheticAdapter(), DatasetRequest(("tp",)), store, schema, "syn2", job_id="job6")
    assert a.checksum == job.checksum  # deterministic generation
    with pytest.raises(ValueError):
        SyntheticAdapter(product="nope")
    assert IMDAAAdapter(tmp_path).name == "IMDAA"
