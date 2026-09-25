"""Ingestion job: source -> checksum -> metadata -> validation -> canonicalisation -> chunking -> Zarr -> metadata.

Every job records: id, source, timestamps, status, per-step status, files with SHA-256, dimensions, variables,
units, geographic and temporal extent, validation findings and any error. Bad data is *quarantined* (its job
record is stored under ``quarantine/``); nothing is deleted or silently discarded.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr

from data_pipeline.adapters.base import AdapterError, DatasetRequest, DataSourceAdapter
from data_pipeline.storage.base import StorageProvider
from data_pipeline.storage.keys import build_key
from data_pipeline.transformation.canonicalize import canonicalize
from data_pipeline.transformation.chunk import chunk_dataset
from data_pipeline.validation.checks import Severity, ValidationSchema, run_validation
from ml.core.provenance import DataKind


class JobStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"


@dataclass
class JobStep:
    name: str
    status: str = "PENDING"
    started_at: str | None = None
    finished_at: str | None = None
    message: str = ""


@dataclass
class IngestionJob:
    job_id: str
    source: str
    data_kind: str
    created_at: str
    dataset_id: str = ""
    status: JobStatus = JobStatus.PENDING
    steps: list[JobStep] = field(default_factory=list)
    files: list[dict[str, Any]] = field(default_factory=list)
    dimensions: dict[str, int] = field(default_factory=dict)
    variables: list[str] = field(default_factory=list)
    units: dict[str, str] = field(default_factory=dict)
    geographic_extent: dict[str, float] | None = None
    temporal_extent: dict[str, str] | None = None
    validation: dict[str, Any] | None = None
    storage_key: str | None = None
    preprocess_config_hash: str | None = None
    checksum: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = str(self.status)
        return d


STEP_NAMES = ("locate_files", "checksum", "open_and_extract_metadata", "validate", "canonicalize", "chunk", "write_zarr", "record_metadata")


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path, block: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(block):
            h.update(chunk)
    return h.hexdigest()


def dataset_fingerprint(ds: xr.Dataset, max_bytes: int = 200_000_000) -> str | None:
    """SHA-256 over variable names and array bytes (for in-memory sources); ``None`` if the dataset is too large."""
    if ds.nbytes > max_bytes:
        return None
    h = hashlib.sha256()
    for name in sorted(ds.data_vars):
        h.update(name.encode())
        h.update(np.ascontiguousarray(ds[name].values).tobytes())
    return h.hexdigest()


def _extent(ds: xr.Dataset) -> tuple[dict[str, float] | None, dict[str, str] | None]:
    geo = temporal = None
    if "latitude" in ds.coords and "longitude" in ds.coords:
        geo = {"south": float(ds.latitude.min()), "north": float(ds.latitude.max()),
               "west": float(ds.longitude.min()), "east": float(ds.longitude.max())}
    if "time" in ds.coords and ds["time"].size:
        t = ds["time"].values.astype("datetime64[s]")
        temporal = {"start": str(t.min()) + "Z", "end": str(t.max()) + "Z"}
    return geo, temporal


def run_ingestion(
    adapter: DataSourceAdapter, request: DatasetRequest, storage: StorageProvider, schema: ValidationSchema,
    dataset_id: str, job_id: str | None = None, data_kind: DataKind | None = None,
    lon_convention: str = "-180_180",
) -> IngestionJob:
    """Run the ingestion steps for ``request`` and persist the job record. Never raises for data problems."""
    desc = adapter.descriptor()
    job = IngestionJob(job_id or uuid.uuid4().hex, desc.name, str(data_kind or desc.data_kind), _now(), dataset_id)
    job.steps = [JobStep(n) for n in STEP_NAMES]
    job.status = JobStatus.RUNNING
    step = {s.name: s for s in job.steps}

    def begin(n: str) -> None:
        step[n].status, step[n].started_at = "RUNNING", _now()

    def end(n: str, msg: str = "", status: str = "SUCCEEDED") -> None:
        step[n].status, step[n].finished_at, step[n].message = status, _now(), msg

    def fail(n: str, msg: str) -> IngestionJob:
        end(n, msg, "FAILED")
        job.status, job.error = JobStatus.FAILED, msg
        _persist(job, storage, quarantine=True)
        return job

    try:
        begin("locate_files")
        files = adapter.source_files(request)
        end("locate_files", f"{len(files)} file(s)")
        begin("checksum")
        job.files = [{"name": p.name, "size": p.stat().st_size, "sha256": sha256_file(p)} for p in files]
        job.checksum = hashlib.sha256("".join(f["sha256"] for f in job.files).encode()).hexdigest() if job.files else None
        end("checksum", "in-memory source: fingerprint computed after open" if not files else "")
        begin("open_and_extract_metadata")
        try:
            ds = adapter.open(request)
        except AdapterError as exc:
            return fail("open_and_extract_metadata", str(exc))
        if not files:
            job.checksum = dataset_fingerprint(ds)
        job.dimensions = {str(k): int(v) for k, v in ds.sizes.items()}
        job.variables = [str(v) for v in ds.data_vars]
        job.units = {str(v): str(ds[v].attrs.get("units", "")) for v in ds.data_vars}
        job.geographic_extent, job.temporal_extent = _extent(canonicalize_coords_only(ds))
        end("open_and_extract_metadata")

        begin("validate")
        source_name = getattr(adapter, "config_key", "") or desc.name
        rep = run_validation(canonicalize_coords_only(ds), schema, source=source_name)
        job.validation = rep.to_dict()
        if not rep.ok:
            errs = "; ".join(f.message for f in rep.findings if f.severity == Severity.ERROR)
            return fail("validate", f"validation failed: {errs}")
        end("validate", f"{len(rep.findings)} finding(s)")

        begin("canonicalize")
        canon = canonicalize(ds, adapter.variable_map(), lon_convention)
        job.preprocess_config_hash = canon.attrs["preprocess_config_hash"]
        end("canonicalize")
        begin("chunk")
        canon = chunk_dataset(canon)
        end("chunk")
        begin("write_zarr")
        key = build_key("staged", desc.name.lower().replace("-", ""), f"{dataset_id}.zarr")
        target, opts = storage.zarr_target(key)
        canon.attrs.update({"data_kind": str(data_kind or desc.data_kind), "source": desc.name, "dataset_id": dataset_id})
        canon.to_zarr(target, mode="w", storage_options=opts, consolidated=False)
        job.storage_key = key
        end("write_zarr", key)
        begin("record_metadata")
        job.status = JobStatus.SUCCEEDED
        _persist(job, storage, quarantine=False)
        end("record_metadata")
        _persist(job, storage, quarantine=False)
    except Exception as exc:  # noqa: BLE001 - job must always end in a recorded state
        job.status, job.error = JobStatus.FAILED, f"unexpected {type(exc).__name__}"
        _persist(job, storage, quarantine=True)
    return job


def canonicalize_coords_only(ds: xr.Dataset) -> xr.Dataset:
    """Rename coordinate aliases so validation sees canonical dimension names (no data changes)."""
    aliases = {"lat": "latitude", "lon": "longitude", "valid_time": "time"}
    return ds.rename({k: v for k, v in aliases.items() if k in ds.variables or k in ds.dims})


def _persist(job: IngestionJob, storage: StorageProvider, quarantine: bool) -> None:
    prefix = "quarantine" if quarantine else "jobs"
    storage.put_bytes(f"{prefix}/{job.job_id}.json", json.dumps(job.to_dict(), indent=2, default=str).encode())
