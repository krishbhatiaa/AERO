"""Run the whole chain on the SYNTHETIC scenario and print a human-readable summary (no server needed).

    python scripts/run_demo.py [--seed 7] [--members 10] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

from app.services import alerts as alert_service  # noqa: E402
from app.services import events as ev  # noqa: E402

from ml.data.synthetic import ScenarioConfig  # noqa: E402
from ml.pipeline.demo import run_demo_pipeline  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--members", type=int, default=10)
    ap.add_argument("--json", type=Path, help="write the event/alert/evaluation summary to this file")
    a = ap.parse_args()
    t0 = time.time()
    r = run_demo_pipeline(ScenarioConfig(seed=a.seed, n_members=a.members), lambda s, f: print(f"  [{f:4.0%}] {s}"))
    summary = ev.event_summary(r, r.primary)
    alert = alert_service.build_alert(r, r.primary)
    print(f"\n=== SYNTHETIC / DEMO DATA (not a real forecast) - finished in {time.time() - t0:.1f}s ===")
    print(f"event      : {summary['event_type']}  severity={summary['severity']} (analytical, NOT official)  confidence={summary['confidence']}")
    print(f"peak       : {summary['peak_intensity']['value']:.0f} mm/6h at T+{summary['peak_lead_hours']}   max area {summary['max_area_km2']:.0f} km2")
    print(f"track      : {len(r.primary.observed_points)} frames, continuity {r.tracking_eval['track_continuity']:.0%}, "
          f"mean centroid error vs true storm centre {r.tracking_eval['mean_error_vs_true_storm_centre_km']:.0f} km")
    h = r.tracking_eval["hindcast"]
    print(f"hindcast   : +1 step  Kalman {h['kalman'][1]:.0f} km vs persistence {h['persistence'][1]:.0f} km (n={h['n'][1]:.0f})")
    print(f"alert      : regions={alert['location']['summary']}  window {alert['forecast_window']['start']} -> {alert['forecast_window']['end']} UTC")
    print("\ndownscaling baselines vs synthetic truth (mean over frames):")
    print(f"  {'method':22} {'RMSE':>7} {'peak err':>9} {'P99 err':>8} {'PSD ratio':>10} {'ext.recall':>10}")
    for row in r.downscaling_eval:
        m = row["metrics"]
        print(f"  {row['method']:22} {m['rmse']['mean']:7.2f} {m['peak_error']['mean']:9.1f} {m['p99_error']['mean']:8.2f} {m['psd_ratio_band']['mean']:10.2f} {m['extreme_recall']['mean']:10.2f}")
    print("\nNo learned model was used or trained. Numbers show interpolation smoothing on synthetic data, not real skill.")
    if a.json:
        a.json.write_text(json.dumps({"event": summary, "alert": alert, "evaluation": [{k: v for k, v in row.items() if k != "per_frame"} for row in r.downscaling_eval]}, indent=2, default=str))
        print(f"wrote {a.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
