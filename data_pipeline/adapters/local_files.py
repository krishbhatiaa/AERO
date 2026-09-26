"""Adapter base that reads user-provisioned NetCDF/GRIB files from ``DATA_PATH/<source>/``."""
from __future__ import annotations

import os
from pathlib import Path

import xarray as xr

from data_pipeline.adapters.base import AccessStatus, AdapterError, DatasetRequest, SourceDescriptor
from ml.core.provenance import DataKind

_NETCDF = {".nc", ".nc4", ".cdf"}
_GRIB = {".grib", ".grb", ".grb2", ".grib2"}


class LocalFileAdapter:
    """Reads local files described by ``config/sources/<key>.yaml``."""

    config_key = ""

    def __init__(self, data_root: Path | str | None = None) -> None:
        self.cfg = self._load()
        self.name = str(self.cfg["source"])
        self.root = Path(data_root or os.environ.get("DATA_PATH", "./var/data")) / "raw" / self.config_key

    def _load(self) -> dict:
        import yaml

        from ml.core.config import config_dir

        with open(config_dir() / "sources" / f"{self.config_key}.yaml", encoding="utf-8") as fh:
            return yaml.safe_load(fh)

    def variable_map(self) -> dict[str, dict[str, str]]:
        return dict(self.cfg.get("variable_map") or {})

    def _local_files(self) -> list[Path]:
        if not self.root.is_dir():
            return []
        return sorted(p for p in self.root.iterdir() if p.suffix.lower() in _NETCDF | _GRIB)

    def descriptor(self) -> SourceDescriptor:
        kind = DataKind(self.cfg["data_kind"])
        res = self.cfg.get("nominal_resolution_deg")
        note = str(self.cfg.get("access", ""))
        if not self.variable_map():
            return SourceDescriptor(self.name, kind, AccessStatus.NOT_CONFIGURED,
                                    f"{self.name}: variable mapping is empty in config/sources/{self.config_key}.yaml. "
                                    "Fill it in from the files you are authorised to use.", res, note)
        if not self._local_files():
            return SourceDescriptor(self.name, kind, AccessStatus.ACCESS_REQUIRED,
                                    f"{self.name}: ACCESS REQUIRED. No local files found; see docs/data_acquisition.md.",
                                    res, note, tuple(self.variable_map()))
        return SourceDescriptor(self.name, kind, AccessStatus.AVAILABLE,
                                f"{self.name}: {len(self._local_files())} local file(s) available.", res, note,
                                tuple(self.variable_map()))

    def source_files(self, request: DatasetRequest) -> list[Path]:
        return list(request.files) if request.files else self._local_files()

    def open(self, request: DatasetRequest) -> xr.Dataset:
        files = [Path(f) for f in self.source_files(request)]
        if not files:
            raise AdapterError(f"{self.name}: no input files. {self.descriptor().message}")
        suffixes = {f.suffix.lower() for f in files}
        try:
            if suffixes <= _NETCDF:
                ds = xr.open_mfdataset(files, engine="netcdf4", combine="by_coords", chunks={})
            elif suffixes <= _GRIB:
                ds = xr.open_mfdataset(files, engine="cfgrib", combine="by_coords", chunks={})
            else:
                raise AdapterError(f"{self.name}: mixed or unsupported file types {sorted(suffixes)}")
        except AdapterError:
            raise
        except ImportError as exc:
            raise AdapterError(f"{self.name}: required reader is not installed ({exc.name}); install the 'grib' extra") from exc
        except Exception as exc:  # noqa: BLE001 - corrupted/unreadable files are reported, not crashed on
            raise AdapterError(f"{self.name}: file could not be read ({type(exc).__name__})") from exc
        if request.variables:
            keep = [v for v in request.variables if v in ds.data_vars]
            ds = ds[keep] if keep else ds
        return ds
