"""Build small, domain-clipped boundary GeoJSON files from Natural Earth.

Natural Earth (https://www.naturalearthdata.com) is public domain. This script
downloads the 1:10m admin-0 and admin-1 GeoJSON files from the
``nvkelso/natural-earth-vector`` GitHub mirror, clips them to a padded
bounding box and simplifies them so the frontend can load them quickly.

NOTE ON BOUNDARIES: Natural Earth depicts disputed areas using its own
conventions. It is NOT a Survey of India compliant dataset. Do not publish
maps built from it as official Indian boundaries (see docs/data_acquisition.md).

Usage:
    python scripts/build_boundaries.py [--src-dir ne_cache] [--out sample_data/boundaries]
"""
from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

from shapely.geometry import box, mapping, shape

BASE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
FILES = ("ne_10m_admin_0_countries", "ne_10m_admin_1_states_provinces")
# Padded bbox: lon_min, lat_min, lon_max, lat_max
BBOX = (76.0, 8.0, 96.0, 28.0)
SIMPLIFY_DEG = 0.004


def _fetch(src_dir: Path, name: str) -> Path:
    path = src_dir / f"{name}.geojson"
    if not path.exists():
        src_dir.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(BASE + name + ".geojson", path)  # noqa: S310 (fixed https URL)
    return path


def _clip(features: list[dict], keep: dict[str, str]) -> list[dict]:
    window = box(*BBOX)
    out: list[dict] = []
    for feat in features:
        geom = shape(feat["geometry"]).intersection(window)
        if geom.is_empty:
            continue
        geom = geom.simplify(SIMPLIFY_DEG, preserve_topology=True)
        props = {new: feat["properties"].get(old) for new, old in keep.items()}
        out.append({"type": "Feature", "properties": props, "geometry": mapping(geom)})
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src-dir", type=Path, default=Path("ne_cache"))
    parser.add_argument("--out", type=Path, default=Path("sample_data/boundaries"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    countries = json.loads(_fetch(args.src_dir, FILES[0]).read_text())["features"]
    states = json.loads(_fetch(args.src_dir, FILES[1]).read_text())["features"]
    india_states = [f for f in states if f["properties"].get("adm0_a3") == "IND"]

    c_out = _clip(countries, {"name": "ADMIN", "iso_a3": "ADM0_A3"})
    s_out = _clip(india_states, {"name": "name", "code": "iso_3166_2"})
    (args.out / "countries_domain.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": c_out}, separators=(",", ":"))
    )
    (args.out / "india_states_domain.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": s_out}, separators=(",", ":"))
    )
    (args.out / "NOTICE.md").write_text(
        "# Boundary data notice\n\n"
        "Source: Natural Earth 1:10m Admin 0 - Countries and Admin 1 - States/Provinces "
        "(public domain, https://www.naturalearthdata.com), obtained from "
        "https://github.com/nvkelso/natural-earth-vector.\n\n"
        f"Clipped to lon/lat box {BBOX} and simplified with tolerance {SIMPLIFY_DEG} degrees.\n\n"
        "**Not an official boundary product.** Natural Earth follows its own conventions for disputed "
        "areas. It is NOT Survey of India compliant. Use official boundaries before any public "
        "deployment (blueprint decision D4).\n"
    )
    print(f"countries: {len(c_out)} features, india states: {len(s_out)} features")


if __name__ == "__main__":
    main()
