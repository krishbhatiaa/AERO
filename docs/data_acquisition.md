# Data acquisition

Rules: use **your own accounts**, respect each provider's licence, never commit credentials or data, never scrape or bypass
access controls. Access routes below were checked at authoring time (September 2026) and can change — verify before relying on them.
Local layout expected by the adapters: `DATA_PATH/raw/<source>/*.nc|*.grib2` (default `./var/data/raw/era5/`).

## ERA5 (development reanalysis) — `ERA5Adapter`
| | |
|---|---|
| Account | Free Copernicus Climate Data Store (CDS) account; accept the ERA5 licence on the dataset page |
| Credentials | Personal access token from your CDS profile. Put it in `~/.cdsapirc` (`url: https://cds.climate.copernicus.eu/api`, `key: <token>`) or `CDSAPI_URL` / `CDSAPI_KEY`. **Never commit.** |
| Install | `pip install cdsapi` (extra `era5`) |
| Command | `python scripts/download_era5.py --start 2021-05-15 --end 2021-05-19 --bbox 70 5 98 26 --variables tp msl u10 v10 t2m --out var/data/raw/era5/tauktae.nc` (`--dry-run` prints the request) |
| Dataset / format | `reanalysis-era5-single-levels`, hourly, NetCDF (`data_format: netcdf`) |
| Native resolution | ≈0.25° (~28–31 km) — **not 12 km**; use it for climatology/anomaly/tracking development, not as a stand-in for NEPS-G |
| Variables & units | `t2m` K · `tp` **metres** of water per accumulation (adapter converts ×1000 → mm) · `msl` Pa · `u10`,`v10` m s⁻¹ · geopotential (if used) m² s⁻² → ÷9.80665 → m |
| Mapping | `config/sources/era5.yaml`; conversion happens in `data_pipeline/transformation/canonicalize.py` |
| Status | request builder unit-tested; **live download not executed here** (no credentials) |

## IMDAA (India regional reanalysis, ~12 km) — `IMDAAAdapter`
| | |
|---|---|
| Access | Registration on the NCMRWF reanalysis data portal (`rds.ncmrwf.gov.in`), intended for research use; follow their terms |
| Expected format | NetCDF/GRIB provided by the portal — the grid is read from the files (published descriptions quote ≈0.12°; do not assume) |
| Adapter | reads files you place in `DATA_PATH/raw/imdaa/`. **`config/sources/imdaa.yaml` has an empty `variable_map` on purpose**: fill in variable names/units from *your* files; until then status is `NOT_CONFIGURED` |
| Use | Climatology baseline for India (configurable period, e.g. 1991–2020) |

## IMD observations — `IMDAdapter`
Follow IMD's data-supply process and terms for gridded rainfall/temperature (e.g. 0.25° daily rainfall). Provide files under
`DATA_PATH/raw/imd/` and fill `config/sources/imd.yaml`. Intended use here: validation of totals, not training labels for the detector.

## NCMRWF NEPS-G / NCUM — `NEPSAdapter`, `NCUMAdapter`
Operational NCMRWF model output is access-controlled. Obtain it **only** through NCMRWF/MoES channels you are authorised to use;
place files under `DATA_PATH/raw/neps/` or `.../ncum/` and fill the `variable_map`. If not available, the API reports
`ACCESS REQUIRED` and names the dataset actually used — it never relabels one dataset as another (see `/api/v1/data-sources`).

## Other open datasets referenced by the roadmap (not bundled)
CHIRPS (0.05° daily precipitation; candidate ~5 km precipitation reference) · IBTrACS (cyclone best tracks; tracking labels) ·
Copernicus DEM / SRTM (terrain conditioning) · IMD district boundaries (official/compliant boundaries are required before any public deployment).

## Bundled sample data
`sample_data/boundaries/` — Natural Earth 1:10m admin-0/admin-1, clipped to the study window (public domain). **Not** a Survey-of-India
compliant boundary set; do not publish maps built from it as official boundaries. Regenerate with `python scripts/build_boundaries.py`.
All weather fields in the demo are generated in-process (`ml/data/synthetic.py`) and labelled SYNTHETIC / DEMO DATA.
