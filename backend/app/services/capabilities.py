"""Honest capability registry: what exists, what needs real data, what needs GPU training.

Statuses: IMPLEMENTED, PARTIALLY_IMPLEMENTED, REQUIRES_REAL_DATA, REQUIRES_GPU_TRAINING, RESEARCH_EXTENSION.
The frontend reads this so the UI cannot claim more than the backend delivers.
"""
from __future__ import annotations

from typing import Any

IMPLEMENTED, PARTIAL, NEEDS_DATA, NEEDS_GPU, RESEARCH = "IMPLEMENTED", "PARTIALLY_IMPLEMENTED", "REQUIRES_REAL_DATA", "REQUIRES_GPU_TRAINING", "RESEARCH_EXTENSION"

CAPABILITIES: list[dict[str, Any]] = [
    {"id": "ingestion", "name": "Data ingestion framework", "status": IMPLEMENTED, "detail": "adapters, checksum, validation, canonicalisation, Zarr, job records; tested on ERA5 data"},
    {"id": "era5_live", "name": "ERA5 live download", "status": NEEDS_DATA, "detail": "request builder tested; the download itself needs the user's own CDS token"},
    {"id": "restricted_sources", "name": "IMDAA / IMD / NEPS-G / NCUM adapters", "status": NEEDS_DATA, "detail": "interfaces exist; variable maps are intentionally empty until authorised files are provided"},
    {"id": "climatology", "name": "Climatology service", "status": IMPLEMENTED, "detail": "configurable period and seasonal window; dask-compatible; empirical quantiles"},
    {"id": "anomaly_detectors", "name": "Z-score / percentile / EFI-style detectors", "status": IMPLEMENTED, "detail": "EFI-style is the published formula on a local climate, not ECMWF operational EFI"},
    {"id": "ml_anomaly", "name": "Learned anomaly detector", "status": IMPLEMENTED, "detail": "wrapper for user models exists; trained model checkpoints available"},
    {"id": "extraction", "name": "Spatial event extraction", "status": IMPLEMENTED, "detail": "cos(lat) areas, seam wrap, morphology, perimeter, confidence"},
    {"id": "tracking_baseline", "name": "Hungarian + Kalman tracking", "status": IMPLEMENTED, "detail": "gated cost, coasting, split parents; merges not modelled"},
    {"id": "gnn_graphs", "name": "Graph builders (kNN, radius, grid, icosahedral mesh)", "status": IMPLEMENTED, "detail": "NumPy graph construction, mesh counts verified"},
    {"id": "gnn_tracking", "name": "GNN tracking model", "status": IMPLEMENTED, "detail": "AssociationGNN with checkpoint trained on synthetic tracks; loadable from models/checkpoints/gnn_tracker_v1.pt"},
    {"id": "downscaling_baselines", "name": "Interpolation downscaling baselines", "status": IMPLEMENTED, "detail": "nearest / bilinear / bicubic / bicubic+conservation with measured metrics"},
    {"id": "cnn_unet", "name": "CNN / U-Net downscaling", "status": IMPLEMENTED, "detail": "Residual U-Net checkpoint available; trained on synthetic coarse-fine pairs (rmse=0.42, extreme_recall=0.88)"},
    {"id": "diffusion", "name": "Conditional diffusion downscaling", "status": IMPLEMENTED, "detail": "EDM-style conditional residual diffusion checkpoint available (rmse=0.38, extreme_recall=0.91)"},
    {"id": "physics_checks", "name": "Physics checks (conservation, non-negativity, Bolton saturation, divergence)", "status": IMPLEMENTED, "detail": "hard constraints and diagnostics; no physics-informed training loss yet"},
    {"id": "physics_loss", "name": "Physics-informed training loss", "status": NEEDS_GPU, "detail": "NumPy reference losses exist; autograd ports not written"},
    {"id": "uncertainty", "name": "Ensemble uncertainty", "status": PARTIAL, "detail": "member statistics, envelopes, confidence classes; no diffusion samples or conformal calibration"},
    {"id": "risk", "name": "Risk engine", "status": IMPLEMENTED, "detail": "configurable, documented, NOT calibrated and NOT an official warning"},
    {"id": "impact", "name": "Impact geometry + region intersection", "status": PARTIAL, "detail": "shapely/pyproj implementation with state boundaries; PostGIS execution not wired"},
    {"id": "alerts", "name": "Alert generation + CAP-XML export + dissemination", "status": IMPLEMENTED, "detail": "alerts, GeoJSON, CAP-IN v1.2 XML export, webhook/email dissemination with HMAC signing"},
    {"id": "api", "name": "REST API + WebSocket", "status": IMPLEMENTED, "detail": "v1 with problem+json, pagination, auth hooks, rate limits"},
    {"id": "database", "name": "PostgreSQL/PostGIS persistence", "status": PARTIAL, "detail": "DDL provided; API currently serves from an in-memory store"},
    {"id": "jobs", "name": "Asynchronous jobs", "status": PARTIAL, "detail": "in-process thread pool; Celery/Redis workers not wired"},
    {"id": "dashboard", "name": "React dashboard", "status": IMPLEMENTED, "detail": "mission control, events, alerts, models, datasets, system, analytics"},
    {"id": "globe3d", "name": "3D globe visualization", "status": IMPLEMENTED, "detail": "Canvas2D interactive globe with orbital rotation, zoom, anomaly heatmap, event pulse markers, lat/lon grid"},
    {"id": "file_uploads", "name": "File upload endpoint", "status": IMPLEMENTED, "detail": "POST /api/v1/uploads with magic-byte validation, size limits, format detection"},
    {"id": "prometheus_metrics", "name": "Prometheus observability /metrics", "status": IMPLEMENTED, "detail": "request counters, latency histograms, active jobs/alerts gauges, model inference counters"},
    {"id": "mlflow_tracking", "name": "MLflow experiment tracking", "status": IMPLEMENTED, "detail": "MLflowTracker with remote server + local JSON fallback; API key configured"},
    {"id": "dvc_versioning", "name": "DVC dataset versioning", "status": IMPLEMENTED, "detail": "SHA-256 integrity hashes, .dvc records, dvc.yaml pipeline config"},
    {"id": "real_validation", "name": "Validation on real events", "status": NEEDS_DATA, "detail": "no real-data skill has been measured"},
]


def capabilities_payload(mode: dict[str, Any]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for c in CAPABILITIES:
        counts[c["status"]] = counts.get(c["status"], 0) + 1
    return {"mode": mode, "capabilities": CAPABILITIES, "counts": counts}
