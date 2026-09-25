"""Download ERA5 single-level fields with YOUR OWN Copernicus CDS account (nothing is bundled or scraped).

Prerequisites (see docs/data_acquisition.md): CDS account, accepted ERA5 licence, personal access token in ~/.cdsapirc or
CDSAPI_URL/CDSAPI_KEY, and `pip install cdsapi`.

    python scripts/download_era5.py --start 2021-05-15 --end 2021-05-19 --bbox 70 5 98 26 --variables tp msl u10 v10 t2m \\
        --out var/data/raw/era5/tauktae_2021-05.nc [--dry-run]

`--dry-run` prints the request body without contacting CDS. This script is NOT exercised against the live CDS here (no
credentials in the authoring environment); the request builder is unit-tested.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data_pipeline.adapters.base import AdapterError, DatasetRequest  # noqa: E402
from data_pipeline.adapters.sources import ERA5Adapter  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", required=True, help="YYYY-MM-DD (UTC)")
    ap.add_argument("--end", required=True, help="YYYY-MM-DD (UTC)")
    ap.add_argument("--bbox", nargs=4, type=float, metavar=("WEST", "SOUTH", "EAST", "NORTH"), required=True)
    ap.add_argument("--variables", nargs="+", default=["tp", "msl", "u10", "v10", "t2m"])
    ap.add_argument("--out", type=Path, default=Path("var/data/raw/era5/era5.nc"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    req = DatasetRequest(tuple(a.variables), datetime.fromisoformat(a.start).replace(tzinfo=UTC), datetime.fromisoformat(a.end).replace(tzinfo=UTC), tuple(a.bbox))
    try:
        body = ERA5Adapter.build_request(req)
        if a.dry_run:
            print(json.dumps(body, indent=2))
            return 0
        path = ERA5Adapter().download(req, a.out)
    except AdapterError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"downloaded {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
