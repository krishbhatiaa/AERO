"""Download ERA5 data via CDS and print a summary of the downloaded file.

Requires a CDS account with ERA5 access, CDSAPI_URL/CDSAPI_KEY or ~/.cdsapirc, and `pip install cdsapi`.

    python scripts/ingest_era5.py --start 2021-05-15 --end 2021-05-19 --region bay-of-bengal [--dry-run]
    python scripts/ingest_era5.py --start 2021-05-15 --end 2021-05-19 --region custom --bbox 70 5 98 26
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data_pipeline.adapters.base import AdapterError, DatasetRequest
from data_pipeline.adapters.sources import ERA5Adapter

REGIONS = {
    "bay-of-bengal": (80.0, 5.0, 98.0, 26.0),
    "eastern-india": (80.0, 15.0, 98.0, 28.0),
    "indian-ocean": (40.0, -10.0, 100.0, 25.0),
    "south-asia": (60.0, 0.0, 100.0, 40.0),
}


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--start", required=True, help="YYYY-MM-DD (UTC)")
    ap.add_argument("--end", required=True, help="YYYY-MM-DD (UTC)")
    ap.add_argument(
        "--region",
        choices=list(REGIONS.keys()) + ["custom"],
        default="bay-of-bengal",
        help="Predefined region or 'custom' with --bbox",
    )
    ap.add_argument(
        "--bbox",
        nargs=4,
        type=float,
        metavar=("WEST", "SOUTH", "EAST", "NORTH"),
        default=None,
        help="Custom bounding box (required when --region=custom)",
    )
    ap.add_argument("--variables", nargs="+", default=["tp", "msl", "u10", "v10"])
    ap.add_argument("--output-dir", type=Path, default=Path("var/raw/era5/"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if a.region == "custom" and a.bbox is None:
        ap.error("--bbox is required when --region=custom")
    bbox = tuple(a.bbox) if a.region == "custom" else REGIONS[a.region]

    start = datetime.fromisoformat(a.start).replace(tzinfo=UTC)
    end = datetime.fromisoformat(a.end).replace(tzinfo=UTC)

    request = DatasetRequest(tuple(a.variables), start, end, tuple(bbox))

    adapter = ERA5Adapter()

    try:
        body = ERA5Adapter.build_request(request)
    except AdapterError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if a.dry_run:
        print(json.dumps(body, indent=2))
        return 0

    date_tag = f"{a.start}_to_{a.end}"
    target_path = a.output_dir / f"era5_{date_tag}.nc"
    target_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        path = adapter.download(request, target_path)
    except AdapterError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"downloaded {path}")

    try:
        ds = adapter.open(DatasetRequest(tuple(a.variables), start, end, tuple(bbox), files=(path,)))
        print(f"variables: {list(ds.data_vars)}")
        print(f"dimensions: {dict(ds.sizes)}")
        if "time" in ds.coords:
            t = ds["time"].values
            print(f"time range: {t[0]} to {t[-1]}")
        elif "valid_time" in ds.coords:
            t = ds["valid_time"].values
            print(f"time range: {t[0]} to {t[-1]}")
        if "latitude" in ds.coords:
            print(f"latitude: {float(ds.latitude.min())} to {float(ds.latitude.max())}")
        if "longitude" in ds.coords:
            print(f"longitude: {float(ds.longitude.min())} to {float(ds.longitude.max())}")
        ds.close()
    except AdapterError as exc:
        print(f"warning: could not verify downloaded file: {exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
