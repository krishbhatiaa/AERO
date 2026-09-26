"""End-to-end demo pipeline on the SYNTHETIC scenario.

data -> climatology -> anomaly detection -> region extraction -> tracking -> ensemble uncertainty
     -> baseline downscaling -> physics checks -> evaluation -> risk -> impact geometry

Every stage is the real implementation used for real data; only the input arrays are synthetic. No trained
model is involved (all components are classical baselines), so nothing here claims learned skill.
"""
from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta

import numpy as np

from ml.anomaly.detectors import EFIStyleDetector, PercentileDetector
from ml.climatology.service import Climatology, ClimatologyConfig, build_climatology, target_dayofyear
from ml.core.config import load_config
from ml.core.geometry import haversine_km
from ml.core.grid import block_mean
from ml.core.provenance import DataKind, Provenance, config_hash
from ml.data.synthetic import ScenarioConfig, SyntheticScenario, generate_scenario
from ml.downscaling.baseline import BaselineDownscaler
from ml.evaluation.metrics import (
    band_power_ratio,
    bias,
    bootstrap_ci,
    correlation,
    extreme_recall_precision,
    extreme_value_bias,
    mae,
    peak_error,
    quantile_error,
    rmse,
)
from ml.extraction.regions import AnomalyRegion, ExtractionConfig, extract_regions
from ml.impact.geometry import RegionIndex, build_impact_geometries
from ml.physics.diagnostics import PhysicsReport, physics_report
from ml.risk.engine import RiskAssessment, RiskEngine, RiskInputs
from ml.tracking.hindcast import hindcast_extrapolation_errors
from ml.tracking.tracker import RegionTracker, Track, TrackerConfig
from ml.uncertainty.ensemble import TrackEnvelope, confidence_class, ensemble_summary, track_envelope

PIPELINE_VERSION = "0.1.0"
MODEL_VERSION = "baselines-v0.1 (percentile + hungarian/kalman + bicubic-conservative)"
Progress = Callable[[str, float], None]


@dataclass
class DemoResult:
    """Everything the API and dashboard need, all computed by real algorithms on synthetic inputs."""

    scenario: SyntheticScenario
    climatology: Climatology
    score: list[np.ndarray]
    regions: list[list[AnomalyRegion]]
    tracks: list[Track]
    primary: Track
    member_positions: np.ndarray  # (M, T, 2) NaN where not detected
    envelopes: list[TrackEnvelope | None]
    member_agreement: list[float]
    efi: list[np.ndarray]
    extrapolation: list[dict[str, float]]
    tracking_eval: dict
    downscaled: dict[str, np.ndarray]
    downscaling_eval: list[dict]
    physics: list[PhysicsReport]
    risk: RiskAssessment
    impact: dict[int, dict]
    provenance: Provenance
    config_digest: str
    diagnostics: list[dict] = field(default_factory=list)

    @property
    def lead_hours(self) -> list[int]:
        return self.scenario.lead_hours

    @property
    def coarse_grid(self):
        return getattr(self.scenario, "coarse_grid", None)


def _detect(det: PercentileDetector, field: np.ndarray, clim: Climatology, grid, ec: ExtractionConfig):
    score = det.score(field, clim)
    regions, diag = extract_regions(score, grid, det.thresholds.moderate, ec, intensity=field)
    return score, regions, diag


def _primary_track(tracks: list[Track]) -> Track:
    return max(tracks, key=lambda t: sum((p.area_km2 or 0.0) for p in t.points))


def run_demo_pipeline(cfg: ScenarioConfig | None = None, progress: Progress | None = None) -> DemoResult:
    """Run the full chain. ``progress(step, fraction)`` is called between stages (used by jobs/WebSocket)."""
    say = progress or (lambda _s, _f: None)
    app_cfg, ds_cfg = load_config("app"), load_config("downscaling")
    anom_cfg = load_config("anomaly")
    say("generate_synthetic_scenario", 0.02)
    sc = generate_scenario(cfg or ScenarioConfig(seed=app_cfg["demo"]["seed"], n_members=app_cfg["demo"]["n_members"]))
    leads, grid = sc.lead_hours, sc.coarse_grid

    say("build_climatology", 0.12)
    doy = target_dayofyear(sc.config.init_time)
    cc = anom_cfg["climatology"]
    clim = build_climatology(
        sc.climate, ClimatologyConfig("tp", tuple(cc["period"]), doy, cc["doy_window_days"], cc["min_samples"], cc["quantile_levels_step"]),
        DataKind.SYNTHETIC_DEMO,
    )

    say("detect_anomalies_and_extract_regions", 0.25)
    det = PercentileDetector()
    tcfg = TrackerConfig.from_yaml()
    xc = load_config("tracking")["extraction"]
    ec = ExtractionConfig(xc["min_area_km2"], xc["closing_iterations"], xc["opening_iterations"], xc["connectivity"])
    scores, frames, diags = [], [], []
    for i, h in enumerate(leads):
        s, regs, d = _detect(det, sc.forecast_coarse["tp"][i], clim, grid, ec)
        scores.append(s)
        frames.append((float(h), regs))
        diags.append({"lead_hours": h, **d})

    say("track_events", 0.40)
    tracks = RegionTracker(tcfg).run(frames)
    if not tracks:
        raise RuntimeError("No events were detected in the control forecast; check climatology/thresholds")
    primary = _primary_track(tracks)

    say("ensemble_uncertainty", 0.50)
    ens = sc.ensemble_coarse["tp"]
    m, t_n = ens.shape[0], len(leads)
    member_pos = np.full((m, t_n, 2), np.nan)
    member_scores = np.zeros((m, t_n) + grid.shape, dtype=np.float32)
    for k in range(m):
        mframes = []
        for i, h in enumerate(leads):
            s, regs, _ = _detect(det, ens[k, i], clim, grid, ec)
            member_scores[k, i] = s
            mframes.append((float(h), regs))
        mtracks = RegionTracker(tcfg).run(mframes)
        if mtracks:
            mp = _primary_track(mtracks)
            for p in mp.points:
                if p.observed:
                    member_pos[k, leads.index(int(p.time_h))] = (p.meas_lat, p.meas_lon)
    envelopes: list[TrackEnvelope | None] = []
    agreement: list[float] = []
    for i, h in enumerate(leads):
        ctrl = next((p for p in primary.points if p.observed and int(p.time_h) == h), None)
        ok = ~np.isnan(member_pos[:, i, 0])
        if ctrl is not None and ok.any():
            near = haversine_km(ctrl.lat, ctrl.lon, member_pos[ok, i, 0], member_pos[ok, i, 1]) <= tcfg.gate_km
            agreement.append(float(near.sum() / m))
        else:
            agreement.append(0.0)
        envelopes.append(track_envelope(member_pos[ok, i]) if ok.sum() >= 2 else None)

    efi_det = EFIStyleDetector()
    efi = [efi_det.score(np.concatenate([sc.forecast_coarse["tp"][i][None], ens[:, i]]), clim) for i in range(t_n)]

    say("extrapolate_and_evaluate_tracking", 0.62)
    last = primary.observed_points[-1]
    extrap = primary.extrapolate(last.time_h, [float(x) for x in app_cfg["demo"]["extrapolation_hours"]])
    truth_centres = {h: (st.lat, st.lon) for h, st in zip(leads, sc.truth_storms, strict=True)}
    errs = [float(haversine_km(p.lat, p.lon, *truth_centres[int(p.time_h)])) for p in primary.observed_points]
    tracking_eval = {
        "n_tracks": len(tracks),
        "primary_track_id": primary.track_id,
        "track_continuity": float(np.mean([p.observed for p in primary.points])),
        "detection_rate": float(len(primary.observed_points) / len(leads)),
        "mean_error_vs_true_storm_centre_km": float(np.mean(errs)),
        "note": (
            "Region centroid of the rain shield is compared with the known synthetic storm centre; a systematic "
            "offset is expected because rainfall is asymmetric about the centre."
        ),
        "hindcast": hindcast_extrapolation_errors(primary, tcfg, 3),
    }

    say("downscale_baselines", 0.72)
    factor = sc.config.refine
    dx_km = float(np.mean(sc.fine_grid.approx_resolution_km()))
    band = tuple(ds_cfg["evaluation"]["spectral_band_km"])
    q = ds_cfg["evaluation"]["extreme_quantile"]
    downscaled: dict[str, np.ndarray] = {}
    rows: list[dict] = []
    truth = sc.truth_fine["tp"]
    for meth in ds_cfg["baseline_methods"]:
        d = BaselineDownscaler(meth)
        downscaled[meth] = np.stack([d.downscale(sc.forecast_coarse["tp"][i], grid, sc.fine_grid) for i in range(t_n)]).astype(np.float32)
        per: dict[str, list[float]] = {k: [] for k in ("mae", "rmse", "bias", "correlation", "peak_error", "extreme_value_bias", "p95_error", "p99_error", "extreme_recall", "extreme_precision", "psd_ratio_band")}
        for i in range(t_n):
            p, tr = downscaled[meth][i].astype(float), truth[i].astype(float)
            rec, prec = extreme_recall_precision(p, tr, q)
            for k, v in (("mae", mae(p, tr)), ("rmse", rmse(p, tr)), ("bias", bias(p, tr)), ("correlation", correlation(p, tr)),
                         ("peak_error", peak_error(p, tr)), ("extreme_value_bias", extreme_value_bias(p, tr, q)),
                         ("p95_error", quantile_error(p, tr, 0.95)), ("p99_error", quantile_error(p, tr, 0.99)),
                         ("extreme_recall", rec), ("extreme_precision", prec), ("psd_ratio_band", band_power_ratio(p, tr, dx_km, band))):
                per[k].append(v)
        metrics = {}
        for k, v in per.items():
            arr = np.array(v, float)
            arr = arr[np.isfinite(arr)]
            lo, hi = bootstrap_ci(arr, n=1000, seed=0) if len(arr) > 1 else (float("nan"), float("nan"))
            metrics[k] = {"mean": float(arr.mean()) if len(arr) else float("nan"), "ci_low": lo, "ci_high": hi}
        rows.append({"method": meth, "metrics": metrics, "n_frames": t_n, "per_frame": {k: [float(x) for x in v] for k, v in per.items()}})

    say("physics_checks", 0.85)
    best = downscaled["bicubic_conservative"]
    phys = [
        physics_report(best[i], sc.forecast_coarse["tp"][i], factor, sc.forecast_coarse["u10"][i], sc.forecast_coarse["v10"][i], grid)
        for i in range(t_n)
    ]

    say("risk_and_impact", 0.92)
    pk = max(primary.observed_points, key=lambda p: p.max_intensity or 0.0)
    pk_i = leads.index(int(pk.time_h))
    step = leads[1] - leads[0] if len(leads) > 1 else 6
    duration = primary.observed_points[-1].time_h - primary.observed_points[0].time_h + step
    env_pk = envelopes[pk_i]
    unc_pk = env_pk.radius_km_p90 if env_pk else pk.uncertainty_radius_km
    risk = RiskEngine().assess(RiskInputs(
        "EXTREME_RAINFALL", float(pk.max_intensity or 0.0), agreement[pk_i], float(duration),
        float(max(p.area_km2 or 0.0 for p in primary.observed_points)), float(pk.time_h), float(unc_pk), agreement[pk_i],
    ))
    index = _region_index()
    impact: dict[int, dict] = {}
    for p in primary.observed_points:
        i = leads.index(int(p.time_h))
        unc = envelopes[i].radius_km_p90 if envelopes[i] else p.uncertainty_radius_km
        geoms = build_impact_geometries((p.lat, p.lon), 0.0, unc, footprint=p.region.footprint)
        impact[int(p.time_h)] = {
            "geometries": geoms, "uncertainty_radius_km": float(unc),
            "regions_impact": index.intersect(geoms["impact"]) if index else [],
            "regions_risk": index.intersect(geoms["risk"]) if index else [],
        }

    digest = config_hash({"anomaly": anom_cfg, "tracking": load_config("tracking"), "risk": load_config("risk"),
                          "downscaling": ds_cfg, "seed": sc.config.seed, "members": sc.config.n_members})
    prov = Provenance(
        data_source="synthetic-scenario-engine", data_kind=DataKind.SYNTHETIC_DEMO,
        dataset_id=f"synthetic-demo-seed{sc.config.seed}", dataset_version=PIPELINE_VERSION,
        initialization_time=sc.config.init_time, model_version=MODEL_VERSION, checkpoint_sha256=None,
        preprocess_config_hash=clim.digest(), pipeline_config_hash=digest, git_sha=os.environ.get("GIT_SHA"),
        notes=["SYNTHETIC / DEMO DATA - not a real forecast or observation",
               f"Geography (land mask): {sc.geography_source}", "No trained ML model is used; all components are classical baselines"],
    )
    say("done", 1.0)
    return DemoResult(sc, clim, scores, [f[1] for f in frames], tracks, primary, member_pos, envelopes, agreement, efi,
                      extrap, tracking_eval, downscaled, rows, phys, risk, impact, prov, digest, diags)


def _region_index() -> RegionIndex | None:
    from ml.data.landmask import DEFAULT_BOUNDARY

    path = DEFAULT_BOUNDARY.parent / "india_states_domain.geojson"
    return RegionIndex.from_geojson(path, "state") if path.is_file() else None


def valid_time(result: DemoResult, lead_h: int):
    """UTC valid time for ``lead_h`` hours after initialisation."""
    return result.scenario.config.init_time + timedelta(hours=lead_h)


__all__ = ["DemoResult", "run_demo_pipeline", "valid_time", "block_mean", "confidence_class", "ensemble_summary"]
