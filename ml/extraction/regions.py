"""Spatial event extraction: threshold -> connected components -> morphology -> region properties.

What   : Turns a gridded anomaly score into discrete regions ("candidate events") with geometry.
Input  : 2-D score array on a :class:`GridSpec`, a threshold, and extraction settings.
Output : list of :class:`AnomalyRegion` (area-weighted centroid, cos(lat)-correct area, perimeter, ...).
Math   : cell areas are exact spherical areas (R^2 dlon (sin phi2 - sin phi1)); centroids are means of
         unit vectors so they are correct across the antimeridian / poles; perimeter sums the exposed
         cell edges using their true lengths (E-W edges shrink with cos(lat)).
Limits : Footprints are unions of grid cells (staircase). Polygons are not antimeridian-split. Regions
         below ``min_area_km2`` are counted in :func:`extract_regions` diagnostics, not silently dropped.
Confidence formula (documented, deterministic):
         conf = 0.5*sat(peak_excess) + 0.3*sat(mean_excess) + 0.2*sat(area / (5*min_area))
         with sat(x) = 1 - exp(-x), excess = (value - thr) / max(|thr|, 1e-9).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import shapely
from scipy import ndimage
from shapely.geometry import mapping
from shapely.geometry.base import BaseGeometry

from ml.core.geometry import EARTH_RADIUS_KM, KM_PER_DEG_LAT, to_local_xy
from ml.core.grid import GridSpec


@dataclass(frozen=True)
class ExtractionConfig:
    """Extraction settings (defaults documented in ``config/tracking.yaml``)."""

    min_area_km2: float = 2000.0
    closing_iterations: int = 1
    opening_iterations: int = 0
    connectivity: int = 8


@dataclass
class AnomalyRegion:
    """One connected anomalous region at one time step."""

    label: int
    centroid_lat: float
    centroid_lon: float
    peak_lat: float
    peak_lon: float
    area_km2: float
    max_intensity: float  # physical intensity (e.g. mm) if supplied, else the score
    mean_intensity: float
    max_score: float  # peak anomaly score inside the region
    mean_score: float
    bbox: tuple[float, float, float, float]  # west, south, east, north (cell edges)
    perimeter_km: float
    compactness: float  # 4*pi*A / P^2, 1 for a circle
    elongation: float  # sqrt(lambda_max / lambda_min) of the second-moment matrix
    confidence: float
    n_cells: int
    footprint: BaseGeometry = field(repr=False, default=None)  # type: ignore[assignment]
    cell_mask: np.ndarray = field(repr=False, default=None)  # type: ignore[assignment]

    def to_geojson_feature(self, **extra: object) -> dict:
        props = {
            "label": self.label, "centroid_lat": self.centroid_lat, "centroid_lon": self.centroid_lon,
            "area_km2": self.area_km2, "max_intensity": self.max_intensity,
            "mean_intensity": self.mean_intensity, "max_score": self.max_score, "mean_score": self.mean_score, "perimeter_km": self.perimeter_km,
            "compactness": self.compactness, "elongation": self.elongation, "confidence": self.confidence,
            **extra,
        }
        return {"type": "Feature", "properties": props, "geometry": mapping(self.footprint)}


def _sat(x: float) -> float:
    return float(1.0 - np.exp(-max(x, 0.0)))


def _merge_across_seam(labels: np.ndarray, n: int, connectivity: int) -> tuple[np.ndarray, int]:
    """Union labels touching across the periodic longitude seam (global grids only)."""
    parent = list(range(n + 1))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    left, right = labels[:, 0], labels[:, -1]
    offsets = (-1, 0, 1) if connectivity == 8 else (0,)
    for i in range(labels.shape[0]):
        if right[i] == 0:
            continue
        for o in offsets:
            j = i + o
            if 0 <= j < labels.shape[0] and left[j] > 0:
                ra, rb = find(int(right[i])), find(int(left[j]))
                if ra != rb:
                    parent[ra] = rb
    roots = np.array([find(i) for i in range(n + 1)])
    uniq = np.unique(roots[1:])
    remap = np.zeros(n + 1, dtype=np.int64)
    for new, root in enumerate(uniq, start=1):
        remap[roots == root] = new
    return remap[labels], len(uniq)


def _perimeter_km(mask: np.ndarray, grid: GridSpec) -> float:
    padded = np.pad(mask, 1, constant_values=False)
    lat_rows = grid.lats
    ew_len = EARTH_RADIUS_KM * np.cos(np.radians(lat_rows)) * np.radians(grid.dlon)  # edge along a parallel
    ns_len = EARTH_RADIUS_KM * np.radians(grid.dlat)  # edge along a meridian
    core = padded[1:-1, 1:-1]
    north_open = core & ~padded[2:, 1:-1]
    south_open = core & ~padded[:-2, 1:-1]
    east_open = core & ~padded[1:-1, 2:]
    west_open = core & ~padded[1:-1, :-2]
    if grid.is_global_lon:
        east_open = core & ~np.roll(core, -1, axis=1)
        west_open = core & ~np.roll(core, 1, axis=1)
    total = ((north_open | south_open) * ew_len[:, None]).sum() + ((east_open | west_open) * ns_len).sum()
    return float(total)


def _centroid(lat: np.ndarray, lon: np.ndarray, w: np.ndarray) -> tuple[float, float]:
    phi, lam = np.radians(lat), np.radians(lon)
    x, y, z = np.cos(phi) * np.cos(lam), np.cos(phi) * np.sin(lam), np.sin(phi)
    xm, ym, zm = np.average(x, weights=w), np.average(y, weights=w), np.average(z, weights=w)
    return float(np.degrees(np.arctan2(zm, np.hypot(xm, ym)))), float(np.degrees(np.arctan2(ym, xm)))


def extract_regions(
    score: np.ndarray, grid: GridSpec, threshold: float, config: ExtractionConfig | None = None,
    intensity: np.ndarray | None = None,
) -> tuple[list[AnomalyRegion], dict[str, int]]:
    """Extract connected regions where ``score >= threshold``.

    Returns ``(regions, diagnostics)``; diagnostics reports how many components were rejected as too
    small so nothing is discarded silently. Regions are sorted by decreasing area. ``intensity`` (same shape)
    supplies physical intensity values (e.g. mm); when omitted the score itself is reported as intensity.
    """
    cfg = config or ExtractionConfig()
    if score.shape != grid.shape:
        raise ValueError(f"score shape {score.shape} does not match grid {grid.shape}")
    s = np.asarray(score, float)
    mask = np.isfinite(s) & (s >= threshold)
    struct = ndimage.generate_binary_structure(2, 2 if cfg.connectivity == 8 else 1)
    if cfg.closing_iterations:
        mask = ndimage.binary_closing(mask, struct, iterations=cfg.closing_iterations, border_value=0) | mask
    if cfg.opening_iterations:
        mask = ndimage.binary_opening(mask, struct, iterations=cfg.opening_iterations)
    labels, n = ndimage.label(mask, structure=struct)
    if grid.is_global_lon and n > 0:
        labels, n = _merge_across_seam(labels, n, cfg.connectivity)

    area = grid.cell_area_km2()
    lon2d, lat2d = np.meshgrid(grid.lons, grid.lats)
    regions: list[AnomalyRegion] = []
    rejected = 0
    finite_s = np.where(np.isfinite(s), s, -np.inf)
    phys = finite_s if intensity is None else np.where(np.isfinite(intensity), intensity, -np.inf)
    for lab in range(1, n + 1):
        cell = labels == lab
        a = float(area[cell].sum())
        if a < cfg.min_area_km2:
            rejected += 1
            continue
        lats, lons, w = lat2d[cell], lon2d[cell], area[cell]
        clat, clon = _centroid(lats, lons, w)
        vals = finite_s[cell]
        peak_i = int(np.argmax(vals))
        maxv, meanv = float(vals[peak_i]), float(np.average(vals, weights=w))
        pvals = phys[cell]
        max_phys, mean_phys = float(pvals.max()), float(np.average(pvals, weights=w))
        per = _perimeter_km(cell, grid)
        x, y = to_local_xy(lats, lons, clat, clon)
        cov = np.cov(np.vstack([x, y]), aweights=w) if cell.sum() > 2 else np.eye(2)
        ev = np.sort(np.clip(np.linalg.eigvalsh(cov), 1e-9, None))
        boxes = shapely.box(lons - grid.dlon / 2, lats - grid.dlat / 2, lons + grid.dlon / 2, lats + grid.dlat / 2)
        fp = shapely.union_all(boxes).simplify(0.25 * min(grid.dlat, grid.dlon), preserve_topology=True)
        thr_scale = max(abs(threshold), 1e-9)
        conf = (
            0.5 * _sat((maxv - threshold) / thr_scale)
            + 0.3 * _sat((meanv - threshold) / thr_scale)
            + 0.2 * _sat(a / (5.0 * cfg.min_area_km2))
        )
        regions.append(
            AnomalyRegion(
                label=lab, centroid_lat=clat, centroid_lon=clon, peak_lat=float(lats[peak_i]),
                peak_lon=float(lons[peak_i]), area_km2=a, max_intensity=max_phys, mean_intensity=mean_phys,
                max_score=maxv, mean_score=meanv,
                bbox=(float(lons.min() - grid.dlon / 2), float(lats.min() - grid.dlat / 2),
                      float(lons.max() + grid.dlon / 2), float(lats.max() + grid.dlat / 2)),
                perimeter_km=per, compactness=float(min(1.0, 4 * np.pi * a / per**2)) if per > 0 else 0.0,
                elongation=float(np.sqrt(ev[1] / ev[0])), confidence=float(conf), n_cells=int(cell.sum()),
                footprint=fp, cell_mask=cell,
            )
        )
    regions.sort(key=lambda r: r.area_km2, reverse=True)
    return regions, {"components": int(n), "rejected_too_small": rejected, "kept": len(regions)}


__all__ = ["AnomalyRegion", "ExtractionConfig", "extract_regions", "KM_PER_DEG_LAT"]
