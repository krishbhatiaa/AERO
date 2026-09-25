"""Baseline event tracker: gated association cost + Hungarian assignment + Kalman smoothing.

What   : Follows the same anomalous region through successive frames (lead times or analysis times).
Cost   : c = w_d * d/gate + w_o * (1 - IoU(advected previous footprint, candidate)) + w_i * |dI|/max(I)
         d is the great-circle distance between the Kalman-predicted centroid and the candidate centroid.
Assign : Hungarian algorithm (scipy.optimize.linear_sum_assignment); pairs costlier than ``max_cost`` or
         beyond ``gate_km`` are rejected. Unmatched tracks coast for ``max_missed`` frames.
Splits : an unmatched new region overlapping an existing track's footprint (IoU > split_overlap_iou)
         starts a new track with ``parent_id`` set. Merges are not modelled (documented limitation).
Output : :class:`Track` objects with filtered position, velocity, speed, bearing, acceleration, area and
         intensity evolution and a 95 % position-uncertainty radius per step.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import linear_sum_assignment
from shapely import affinity

from ml.core.config import load_config
from ml.core.geometry import KM_PER_DEG_LAT, bearing_deg, from_local_xy, haversine_km, to_local_xy
from ml.extraction.regions import AnomalyRegion
from ml.tracking.kalman import ConstantVelocityKalman

_BIG = 1e6


@dataclass(frozen=True)
class TrackerConfig:
    w_distance: float = 0.5
    w_overlap: float = 0.3
    w_intensity: float = 0.2
    gate_km: float = 300.0
    max_cost: float = 1.0
    max_missed: int = 1
    split_overlap_iou: float = 0.05
    sigma_meas_km: float = 12.0
    sigma_accel_kmh2: float = 1.5
    sigma_v0_kmh: float = 30.0

    @classmethod
    def from_yaml(cls) -> TrackerConfig:
        c = load_config("tracking")
        a, k = c["association"], c["kalman"]
        return cls(
            w_distance=a["weights"]["distance"], w_overlap=a["weights"]["overlap"],
            w_intensity=a["weights"]["intensity"], gate_km=a["gate_km"], max_cost=a["max_cost"],
            max_missed=a["max_missed"], split_overlap_iou=a["split_overlap_iou"],
            sigma_meas_km=k["sigma_meas_km"], sigma_accel_kmh2=k["sigma_accel_kmh2"], sigma_v0_kmh=k["sigma_v0_kmh"],
        )


@dataclass
class TrackPoint:
    """One time step of a track. ``observed=False`` marks a coasted (predicted, not detected) step."""

    time_h: float
    lat: float
    lon: float
    meas_lat: float | None
    meas_lon: float | None
    speed_kmh: float
    bearing_deg: float
    accel_kmh2: float
    area_km2: float | None
    max_intensity: float | None
    mean_intensity: float | None
    confidence: float | None
    uncertainty_radius_km: float
    observed: bool
    region: AnomalyRegion | None = field(default=None, repr=False)


@dataclass
class Track:
    """A tracked event: ordered points plus filter state."""

    track_id: int
    origin: tuple[float, float]
    kf: ConstantVelocityKalman
    points: list[TrackPoint] = field(default_factory=list)
    active: bool = True
    missed: int = 0
    parent_id: int | None = None

    @property
    def last(self) -> TrackPoint:
        return self.points[-1]

    @property
    def observed_points(self) -> list[TrackPoint]:
        return [p for p in self.points if p.observed]

    @property
    def peak_intensity(self) -> float:
        vals = [p.max_intensity for p in self.points if p.max_intensity is not None]
        return float(max(vals)) if vals else float("nan")

    def extrapolate(self, from_time_h: float, target_times_h: list[float]) -> list[dict[str, float]]:
        """Kalman extrapolation of the track. This is a *baseline extrapolation*, not a physical forecast."""
        out: list[dict[str, float]] = []
        for t in target_times_h:
            x, p = self.kf.predicted(t - from_time_h)
            lat, lon = from_local_xy(x[0], x[1], *self.origin)
            out.append({
                "time_h": float(t), "lat": float(lat), "lon": float(lon),
                "uncertainty_radius_km": self.kf.position_radius_km(p),
                "speed_kmh": float(np.hypot(x[2], x[3])),
            })
        return out


def _iou(a, b) -> float:
    if a is None or b is None or a.is_empty or b.is_empty:
        return 0.0
    inter = a.intersection(b).area
    union = a.union(b).area
    return float(inter / union) if union > 0 else 0.0


class RegionTracker:
    """Frame-by-frame tracker. Call :meth:`step` once per frame in chronological order."""

    def __init__(self, config: TrackerConfig | None = None) -> None:
        self.cfg = config or TrackerConfig()
        self.tracks: list[Track] = []
        self._next_id = 1

    # -- helpers -----------------------------------------------------------------------------------
    def _predicted_latlon(self, t: Track, dt: float) -> tuple[float, float, np.ndarray]:
        x, _ = t.kf.predicted(dt)
        lat, lon = from_local_xy(x[0], x[1], *t.origin)
        return float(lat), float(lon), x

    def _cost(self, t: Track, r: AnomalyRegion, dt: float) -> float | None:
        plat, plon, _ = self._predicted_latlon(t, dt)
        dist = float(haversine_km(plat, plon, r.centroid_lat, r.centroid_lon))
        if dist > self.cfg.gate_km:
            return None
        prev = t.last
        shift_lat = plat - prev.lat
        shift_lon = plon - prev.lon
        prev_fp = prev.region.footprint if prev.region is not None else None
        adv = affinity.translate(prev_fp, xoff=shift_lon, yoff=shift_lat) if prev_fp is not None else None
        c_o = 1.0 - _iou(adv, r.footprint)
        pi, ri = prev.max_intensity, r.max_intensity
        c_i = 0.0 if pi is None else abs(pi - ri) / max(abs(pi), abs(ri), 1e-9)
        c = self.cfg.w_distance * dist / self.cfg.gate_km + self.cfg.w_overlap * c_o + self.cfg.w_intensity * c_i
        return float(c)

    def _new_track(self, time_h: float, r: AnomalyRegion, parent: int | None) -> Track:
        c = self.cfg
        kf = ConstantVelocityKalman(0.0, 0.0, c.sigma_meas_km, c.sigma_accel_kmh2, c.sigma_v0_kmh)
        tr = Track(self._next_id, (r.centroid_lat, r.centroid_lon), kf, parent_id=parent)
        self._next_id += 1
        tr.points.append(self._point(tr, time_h, r, r.centroid_lat, r.centroid_lon, 0.0, True))
        return tr

    def _point(self, t: Track, time_h: float, r: AnomalyRegion | None, mlat: float | None,
               mlon: float | None, accel: float, observed: bool) -> TrackPoint:
        x = t.kf.x
        lat, lon = from_local_xy(x[0], x[1], *t.origin)
        speed = float(np.hypot(x[2], x[3]))
        if speed > 1e-6:  # bearing measured at the object's own location (not in the track's origin frame)
            nlat, nlon = from_local_xy(x[0] + x[2], x[1] + x[3], *t.origin)
            brg = float(bearing_deg(lat, lon, nlat, nlon))
        else:
            brg = 0.0
        return TrackPoint(
            time_h=time_h, lat=float(lat), lon=float(lon), meas_lat=mlat, meas_lon=mlon,
            speed_kmh=speed, bearing_deg=brg,
            accel_kmh2=accel, area_km2=None if r is None else r.area_km2,
            max_intensity=None if r is None else r.max_intensity,
            mean_intensity=None if r is None else r.mean_intensity,
            confidence=None if r is None else r.confidence,
            uncertainty_radius_km=t.kf.position_radius_km(), observed=observed, region=r,
        )

    # -- public API --------------------------------------------------------------------------------
    def step(self, time_h: float, regions: list[AnomalyRegion]) -> dict[int, int]:
        """Associate ``regions`` (detected at ``time_h``) with tracks. Returns ``{track_id: region_index}``."""
        active = [t for t in self.tracks if t.active]
        prev_footprints = [(t.track_id, t.last.region.footprint) for t in self.tracks if t.points and t.last.region is not None]
        matches: dict[int, int] = {}
        if active and regions:
            cost = np.full((len(active), len(regions)), _BIG)
            for i, t in enumerate(active):
                dt = time_h - t.last.time_h
                for j, r in enumerate(regions):
                    c = self._cost(t, r, dt)
                    if c is not None:
                        cost[i, j] = c
            rows, cols = linear_sum_assignment(cost)
            matches = {int(i): int(j) for i, j in zip(rows, cols, strict=True) if cost[i, j] <= self.cfg.max_cost}

        result: dict[int, int] = {}
        for i, t in enumerate(active):
            dt = time_h - t.last.time_h
            prev_v = t.kf.x[2:].copy()
            t.kf.predict(dt)
            if i in matches:
                r = regions[matches[i]]
                mx, my = to_local_xy(r.centroid_lat, r.centroid_lon, *t.origin)
                t.kf.update(float(mx), float(my))
                accel = float(np.linalg.norm(t.kf.x[2:] - prev_v) / dt) if dt > 0 else 0.0
                t.points.append(self._point(t, time_h, r, r.centroid_lat, r.centroid_lon, accel, True))
                t.missed = 0
                result[t.track_id] = matches[i]
            else:
                t.missed += 1
                if t.missed > self.cfg.max_missed:
                    t.active = False
                else:
                    t.points.append(self._point(t, time_h, None, None, None, 0.0, False))

        used = set(matches.values())
        for j, r in enumerate(regions):
            if j in used:
                continue
            parent = None
            for tid, fp in prev_footprints:  # footprints from *before* this frame's update
                if _iou(fp, r.footprint) > self.cfg.split_overlap_iou:
                    parent = tid
                    break
            tr = self._new_track(time_h, r, parent)
            self.tracks.append(tr)
            result[tr.track_id] = j
        return result

    def run(self, frames: list[tuple[float, list[AnomalyRegion]]]) -> list[Track]:
        """Track through ``[(time_h, regions), ...]`` and return all tracks."""
        for time_h, regions in frames:
            self.step(time_h, regions)
        return self.tracks


__all__ = ["RegionTracker", "Track", "TrackPoint", "TrackerConfig", "KM_PER_DEG_LAT"]
