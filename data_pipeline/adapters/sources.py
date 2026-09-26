"""Concrete adapters: ERA5, IMDAA, IMD, NEPS-G, NCUM.
All sources must be real data. No synthetic fallback is permitted.
"""
from __future__ import annotations

import os
from pathlib import Path

import xarray as xr

from data_pipeline.adapters.base import AccessStatus, AdapterError, DatasetRequest, SourceDescriptor
from data_pipeline.adapters.local_files import LocalFileAdapter

ERA5_SINGLE_LEVELS = "reanalysis-era5-single-levels"
# ERA5 short name -> CDS long name (single-level variables used by this project)
_ERA5_CDS_NAMES = {
    "t2m": "2m_temperature", "tp": "total_precipitation", "msl": "mean_sea_level_pressure",
    "u10": "10m_u_component_of_wind", "v10": "10m_v_component_of_wind",
}


class ERA5Adapter(LocalFileAdapter):
    """ERA5 reanalysis. Reads local NetCDF/GRIB; can build (and, with the user's own CDS token, run) a CDS request."""

    config_key = "era5"

    def descriptor(self) -> SourceDescriptor:
        d = super().descriptor()
        if d.status == AccessStatus.ACCESS_REQUIRED and self._cds_configured():
            return SourceDescriptor(d.name, d.data_kind, AccessStatus.DOWNLOADABLE,
                                    "ERA5: no local files yet, but CDS credentials are configured; run scripts/download_era5.py.",
                                    d.nominal_resolution_deg, d.access_note, d.variables)
        return d

    @staticmethod
    def _cds_configured() -> bool:
        return bool(os.environ.get("CDSAPI_KEY")) or Path.home().joinpath(".cdsapirc").is_file()

    @staticmethod
    def build_request(request: DatasetRequest) -> dict:
        """Deterministic CDS API request body for ``request`` (pure function; no network)."""
        if not request.variables or request.start is None or request.end is None:
            raise AdapterError("ERA5 request needs variables, start and end")
        unknown = [v for v in request.variables if v not in _ERA5_CDS_NAMES]
        if unknown:
            raise AdapterError(f"ERA5 variable(s) not supported by this adapter: {unknown}")
        days = sorted({(request.start.date().toordinal() + i) for i in range((request.end.date() - request.start.date()).days + 1)})
        from datetime import date

        dates = [date.fromordinal(d) for d in days]
        body: dict = {
            "product_type": ["reanalysis"],
            "variable": [_ERA5_CDS_NAMES[v] for v in request.variables],
            "year": sorted({f"{d.year:04d}" for d in dates}),
            "month": sorted({f"{d.month:02d}" for d in dates}),
            "day": sorted({f"{d.day:02d}" for d in dates}),
            "time": [f"{h:02d}:00" for h in range(24)],
            "data_format": "netcdf",
            "download_format": "unarchived",
        }
        if request.bbox is not None:
            w, s, e, n = request.bbox
            body["area"] = [n, w, s, e]  # CDS order: North, West, South, East
        return body

    def download(self, request: DatasetRequest, target: Path) -> Path:
        """Download via the user's own CDS account. Requires ``pip install cdsapi`` and a personal token."""
        try:
            import cdsapi
        except ImportError as exc:
            raise AdapterError("cdsapi is not installed; install the 'era5' extra") from exc
        if not self._cds_configured():
            raise AdapterError("CDS credentials not found (set CDSAPI_URL/CDSAPI_KEY or create ~/.cdsapirc)")
        target.parent.mkdir(parents=True, exist_ok=True)
        client = cdsapi.Client(timeout=180, sleep_max=5)
        client.retrieve(ERA5_SINGLE_LEVELS, self.build_request(request), str(target))

        # CDS returns a .zip archive when requests contain mixed step types (e.g. instantaneous + accumulated)
        import shutil
        import tempfile
        import zipfile

        if zipfile.is_zipfile(target):
            with tempfile.TemporaryDirectory() as tmpdir:
                with zipfile.ZipFile(target, "r") as z:
                    z.extractall(tmpdir)
                nc_files = sorted(Path(tmpdir).glob("*.nc"))
                if nc_files:
                    datasets = [xr.open_dataset(f) for f in nc_files]
                    try:
                        merged = xr.merge(datasets, compat="override")
                        tmp_out = Path(tmpdir) / "merged.nc"
                        merged.to_netcdf(tmp_out)
                        merged.close()
                        for ds in datasets:
                            ds.close()
                        shutil.move(str(tmp_out), str(target))
                    except Exception as err:
                        for ds in datasets:
                            ds.close()
                        raise AdapterError(f"Failed to merge multi-stream CDS NetCDF files: {err}") from err

        return target

    def download_batch(self, requests: list[DatasetRequest], target_dir: Path) -> list[Path]:
        """Download multiple CDS requests, returning a list of downloaded file paths."""
        paths: list[Path] = []
        for i, req in enumerate(requests):
            date_tag = f"{req.start.date()}_{req.end.date()}" if req.start and req.end else f"batch_{i}"
            target = target_dir / f"era5_{date_tag}.nc"
            paths.append(self.download(req, target))
        return paths

    @staticmethod
    def verify_download(path: Path, expected_vars: list[str] | tuple[str, ...] | None = None) -> bool:
        """Return True if *path* is a readable NetCDF file containing expected ERA5 variables."""
        import zipfile
        if not path.is_file() or zipfile.is_zipfile(path):
            return False
        try:
            import xarray as xr

            with xr.open_dataset(path, engine="netcdf4") as ds:
                if expected_vars:
                    return all(v in ds.data_vars for v in expected_vars)
                return any(v in ds.data_vars for v in _ERA5_CDS_NAMES.keys())
        except Exception:  # noqa: BLE001
            return False


class IMDAAAdapter(LocalFileAdapter):
    config_key = "imdaa"


class IMDAdapter(LocalFileAdapter):
    config_key = "imd"


class NEPSAdapter(LocalFileAdapter):
    config_key = "neps"


class NCUMAdapter(LocalFileAdapter):
    config_key = "ncum"


class SyntheticAdapter(LocalFileAdapter):
    config_key = "synthetic"


ADAPTERS: dict[str, type] = {
    "era5": ERA5Adapter, "imdaa": IMDAAAdapter, "imd": IMDAdapter, "neps": NEPSAdapter, "ncum": NCUMAdapter, "synthetic": SyntheticAdapter,
}
