# understanding.md — everything explained, from first principles

Audience: a software engineer with little meteorology background, a judge who wants the honest picture, or a new team member.
Every concept is tied to the file that implements it. Numbers quoted from the demo are **synthetic**.

---
## 0. The problem in one page

**PS 26078 (MoES / NCMRWF):** medium-range forecasts (days 1–10) come from NWP models at ~12 km. Extreme events — cyclones, extreme rainfall,
heatwaves — are (a) **smoothed** by the coarse grid and by regression-trained AI, (b) **uncertain** (many plausible futures), and (c) need to be
turned into **localized** decision support. The project asks for: detect anomalies → track them through time → predict trajectories →
downscale 12 → 5 km without smoothing the extremes → keep the physics honest → quantify uncertainty → produce localized alerts.

**What this repository is:** the complete *platform and evaluation harness* for that chain, with a classical baseline at every stage, a synthetic
scenario engine so it runs anywhere, and the interfaces where real data and learned models plug in. **What it is not:** a trained AI. The
GNN/diffusion models are designed (interfaces, graph mesh, losses as NumPy references) but not trained, because that needs GPUs and real
fine-resolution data. We chose to *not fake it*.

---
## 1. Weather-data fundamentals

| Concept | Plain explanation | Where in the code |
|---|---|---|
| **Grid** | Weather models divide the atmosphere into cells. A field (e.g. rainfall) is a 2-D array on a lat/lon grid; a dataset adds time, variable, level, ensemble member. Resolution is metadata: 12 km ≈ 0.11°. | `ml/core/grid.py` (`GridSpec`) |
| **Cell area** | Cells shrink toward the poles (∝ cos φ). Never count pixels; use exact spherical areas. | `GridSpec.cell_area_km2` |
| **NetCDF / GRIB2 / Zarr** | NetCDF: self-describing array files (dims, coords, units). GRIB2: compact meteorological format (needs eccodes/cfgrib). Zarr: chunked cloud-friendly arrays — what we write to object storage. | `data_pipeline/adapters/local_files.py`, `ingestion/pipeline.py` |
| **Xarray / Dask** | Xarray = labelled N-D arrays; Dask = lazy, chunked, parallel computation, so a multi-GB dataset is never fully in RAM. | climatology, canonicalisation, chunking |
| **Observation** | What was measured. | `DataKind.OBSERVED` |
| **Reanalysis** | A model + all observations re-run over decades into a physically consistent history (ERA5 ~28 km, IMDAA ~12 km over India). Best "what normal looks like". | `REANALYSIS`, ERA5/IMDAA adapters |
| **NWP forecast** | A model integration from today's analysis. NEPS-G (ensemble) and NCUM (deterministic) are NCMRWF's. | `FORECAST` |
| **Ensemble** | Many forecasts from perturbed starts; their spread = uncertainty. Never present one member as certain. | `ml/uncertainty/ensemble.py` |
| **Climatology** | The historical distribution for this time of year (mean, std, quantiles), from a configurable period like 1991–2020. | `ml/climatology/service.py` |
| **Anomaly** | Deviation from climatology: z-score `(x−μ)/σ`, or percentile rank. | `ml/anomaly/detectors.py` |
| **EFI** | ECMWF's Extreme Forecast Index: compares the ensemble's distribution with the model climate, −1…+1. We implement the *published formula*, not ECMWF's operational product. | `EFIStyleDetector` |
| **Downscaling** | Turning coarse fields into finer ones. | `ml/downscaling/baseline.py` |
| **Tracking** | Recognising "the same" weather system in successive frames. | `ml/tracking/` |

**Provenance labels** (`ml/core/provenance.py`): `OBSERVED · REANALYSIS · FORECAST · MODEL_PREDICTION · SYNTHETIC_DEMO`. `combine_kinds()` returns the
*weakest* label of any input, so a product built from synthetic data can never look real. The UI shows the badge on every layer.

---
## 2. The pipeline, stage by stage (what it does, what comes out)

`ml/pipeline/demo.py` runs all of it in ~5 s on one CPU. Outputs quoted are from the default synthetic scenario (seed 7).

1. **Ingestion** (`data_pipeline/ingestion/pipeline.py`): locate files → SHA-256 → open lazily → extract metadata (dims, variables, units, extents) →
   **validate** (missing dims/vars, lat/lon range, duplicates, non-monotonic axes, unit mismatch, NaN-heavy fields, out-of-range values, duplicate/irregular
   timestamps, incompatible grid) → canonicalise (canonical names, units, lon wrap, lat sort) → chunk → write Zarr → job record. Bad data is **quarantined
   with its reasons**, never silently discarded. *Tests found a real bug here:* extents were empty for `lat/lon/valid_time` naming.
2. **Climatology**: 30 years × ±7 days pooled samples → mean/std/99 quantiles per cell (synthetic sample: 450 fields).
3. **Anomaly**: percentile rank vs climatology (precipitation is skewed, so not z-score). Score ≥ P95 = "moderate", ≥ P99 = "extreme" (thresholds in YAML).
4. **Event extraction**: mask → closing → connected components → regions with centroid, cos-lat area, max/mean intensity, perimeter, compactness, confidence.
5. **Tracking**: cost = distance + (1 − overlap) + intensity change, Hungarian assignment, Kalman filter → speed, bearing, acceleration, area/intensity
   evolution, 95 % position radius. Demo: one track through all 9 frames; centroid within 25 km of the true storm centre on average.
6. **Trajectory prediction**: (a) constant-velocity extrapolation beyond the last frame (dashed, labelled *extrapolation*), (b) hindcast evaluation against
   persistence (Kalman 25 km vs 88 km at +6 h, n=6 — a mechanics check, not a skill claim).
7. **Ensemble uncertainty**: 10 perturbed synthetic members → per-lead position spread (p90 radius ~25 → 170 km), member agreement, EFI-style index,
   confidence class (HIGH/MEDIUM/LOW, thresholds documented).
8. **Downscaling (baselines)**: nearest, bilinear, bicubic, bicubic + conservation (block means forced to equal the coarse value, no negative rain).
9. **Physics checks**: non-negativity, coarse-cell conservation, 10 m wind divergence, Bolton saturation (module) — reported per product.
10. **Evaluation**: 11 metrics + spectra with bootstrap CIs vs the synthetic fine truth. **Finding:** every interpolation under-predicts the peak
    (−10 to −34 mm/6h); conservation helps most. That gap is what a learned downscaler must close.
11. **Risk**: rule-based composite score → LOW/MODERATE/SEVERE (analytical, not official) + rationale + confidence class.
12. **Impact geometry**: footprint, footprint ⊕ R68, footprint ⊕ R95 → intersect administrative regions (Odisha, Jharkhand, West Bengal in the demo).
13. **Alert**: event id/type/severity/location/affected area/window/probability/confidence/uncertainty/source/model version/timestamp + verification note.

---
## 3. The ML ideas (and what exists)

**Why not just a CNN on a lat/lon image?** The lat/lon grid over-samples the poles, distorts distances, and cuts the globe at ±180°. Weather fields are
*scientific tensors on a sphere*, not photographs.

**GNN.** Represent the domain as a graph: nodes = points (features: lat/lon as 3-D unit vector, temperature, pressure, humidity, wind, rainfall, geopotential,
anomaly score), edges = spatial neighbours (k-NN, radius, grid, or **icosahedral mesh**). Message passing lets each node update from its neighbours;
add a temporal encoder (GRU by default, or a temporal Transformer — *choose by benchmark, not fashion*).
*Implemented:* the graph builders (`ml/gnn/graphs.py`) — icosahedral mesh with V = 10·4ᴸ+2 (L=6 → 40 962 nodes), grid↔mesh wiring, edge features in local tangent frames.
*Not implemented:* the model (encoder–processor–decoder), training, and the tracking heads (probability, centroid, radius, trajectory, uncertainty).

**Downscaling and "spectral smoothing".** A network trained with MSE learns the *conditional mean*: when several fine-scale patterns fit the same coarse input,
the mean of them is blurry, and extremes vanish. Remedies: extreme-weighted losses; probabilistic generation (diffusion) that samples *many plausible* fine
fields. **Diffusion is not "automatically more accurate"** — the plan is to compare U-Net vs diffusion on peak error, P99 error, power spectrum and CRPS, and
report whichever wins per metric. *Implemented:* the baselines, the metric suite (peak/quantile/spectral/CRPS), NumPy reference losses (MSE, MAE, Huber,
Quantile, ExtremeWeighted — e.g. predicting 80 mm when 200 mm fell costs 4× an equal error at an ordinary value). *Not implemented:* CNN, U-Net, diffusion, PyTorch loss ports.

**Physics-informed learning.** Add penalties for violating known relations. We only include relations we can define rigorously (conservation of coarse totals,
non-negativity, saturation bound, divergence diagnostics), each documented with units/assumptions/reference/tests in `docs/science.md`. We do **not** invent equations.

**Uncertainty.** Three separable sources: initial-condition (ensemble members), downscaling (diffusion samples — not yet), tracking (filter covariance).
The envelope is a percentile envelope of member positions, deliberately **not** called an NHC cone.

---
## 4. Geospatial + database

* **PostGIS** stores geometries (events, footprints, impact polygons, administrative regions) with **GIST indexes**; `ST_Intersects` uses the index, then exact
  intersection; area uses `::geography` (true ellipsoidal km²). Big arrays stay in object storage as Zarr — never in PostgreSQL.
* `database/schema/001_init.sql` — 25 tables (events, tracks, forecast runs/members, anomaly regions, impact geometries, downscaled products, model registry,
  alerts, alert regions, geographic regions, sources, ingestion jobs/steps/findings, users, append-only audit log). Applied and tested on PostgreSQL 16 / PostGIS 3.4;
  `scripts/seed_db.py` loads the demo and asserts PostGIS = shapely to within 2 %.
* **Current limitation:** the API serves from an in-memory `ProductStore`; DB-backed repositories are the next platform batch.

---
## 5. Architecture

```
Browser (React/TS) ── REST /api/v1 + WebSocket ──► FastAPI (request-id, CORS, rate-limit, body-limit, secure headers, auth hook)
                                                      │ routers → services → ProductStore (in-memory today; PostGIS later)
                                                      ├─ JobManager (thread pool; Celery later) ──► ml.pipeline.demo.run_demo_pipeline
                                                      ├─ Cache (Redis if reachable, else memory) / Audit log (JSON lines)
                                                      └─ StorageProvider (Local | S3/MinIO) ◄── data_pipeline (adapters, validation, ingestion)
ml/  (pure scientific code, no web imports)      config/ (thresholds, units, source maps)      database/ (PostGIS DDL)
```
* **Security:** env-only secrets (`SecretStr`), API-key auth (SHA-256 digests, constant-time compare) with roles, RBAC on mutating routes, sliding-window
  rate limit, streaming body-size limit, secure headers, explicit CORS (no `*`), path-traversal-safe storage keys (and symlink escape blocked), problem+json
  without internals, append-only audit log, WebSocket auth by first message (keys never in URLs).
* **Observability:** JSON logs with request/job ids, `/live`, `/health`, `/ready` (per-dependency, no URLs/credentials leaked), audit trail.
* **Time:** UTC in the backend; the UI shows UTC + IST + chosen zone, always labelled (`frontend/src/lib/time.ts`).

---
## 6. Frontend design language

Derived from your two mockups: the **workstation** (light, dense, Inter + JetBrains Mono, thin borders, tool dock, layer list, right-hand analysis panels,
bottom time machine) and the **platform** landing (dark, cyan primary, bento cards). Both themes are CSS-variable token sets generated from the mockups
(`frontend/scripts/gen-tokens.py`); every text/background pair is unit-tested for WCAG AA contrast.

**Deliberately not copied from the mockups** (they would violate the honesty rules): "ISO 27001 / STQC / MeitY / CAP-IN v1.2 certified", "97.4 % amplitude
preserved", "1.84 s on H100", "1000× acceleration", the named duty officer, fake radar/SST layers, a hand-drawn coastline, hard-coded cyclone bulletins.
Their *layout, tokens and typography* are used; every number is fetched from the API. Material Symbols/Google Fonts CDNs were replaced by bundled
lucide icons and `@fontsource` fonts so the app works offline and under a strict CSP.

**Map:** canvas rasters with smoothing disabled (each model cell stays visible — that *is* the 12-vs-5 km point), SVG vectors in data space under one transform
(pan/zoom never recomputes geometry), equirectangular projection with an 18°N standard parallel (stated on screen). The wipe divider follows the event and
is a keyboard-operable slider. Tools: pan, probe (reads real values), measure (great-circle).
**Accessibility:** semantic landmarks, skip link, labelled controls, focus-visible, reduced-motion, charts with table alternatives, severity = icon + text + border weight.
**Async states:** every data block renders loading / success / empty / partial / error / offline.

---
## 7. Decisions and deviations (blueprint → implementation)

| Blueprint decision | What was done |
|---|---|
| D1 5 km truth: synthetic + CHIRPS | Synthetic implemented; CHIRPS pairs not yet |
| D2 labels: IBTrACS | not yet (needs download) |
| D3 compute: design for 1 GPU | everything runs on CPU; no torch dependency in the shipped baselines |
| D4 boundaries: Natural Earth | done, with prominent "not official" notices |
| D5 real demo event: Tauktae | not done (needs ERA5 download with your token) |
| D6 jobs: Celery | in-process thread pool with the same job model |
| Synthetic engine in Phase 4 | done (needed for a runnable demo) |
| Tests per phase | done; a further real-browser accessibility audit was added |

**Bugs the tests found (and fixed) — evidence that the tests are doing work:** longitude wrap returned exactly 360.0 for `-3e-23`; leap years silently dropped
climatology samples; track bearing was measured in the wrong frame (≈4° off); split detection compared against the already-updated footprint; dataset extents
were empty for ERA5-style names; S3 swallowed key-validation errors; extreme masks were degenerate for zero-inflated fields; chart axes stopped below the data peak;
buttons lost their descriptive accessible name; `<dl>` contained invalid children; legend labels had 2.1:1 contrast.

---
## 8. Explain it at three levels
* **Child:** "The computer finds big storms in weather maps, follows them, zooms in, and says how sure it is."
* **Engineer:** the chain in §2, with a baseline at each stage, evaluation before claims, provenance labels, PostGIS for geometry, Zarr for arrays.
* **Scientist:** climatological percentile/EFI-style detection → object tracking with a constant-velocity Kalman filter → conservative downscaling baselines evaluated on
  extremes and spectra (with a plan for CorrDiff-style residual diffusion) → ensemble-based uncertainty → analytical risk and geometry-based impact.

## 9. Glossary
**Anomaly** deviation from normal · **Ensemble** set of forecasts · **EFI** extreme forecast index · **GIST** spatial index · **Hungarian algorithm** optimal one-to-one matching ·
**IoU** overlap ratio · **Kalman filter** optimal recursive state estimator · **NWP** numerical weather prediction · **PSD** power spectral density (how much variance at each length scale) ·
**CRPS** ensemble accuracy score · **Reanalysis** model-consistent historical reconstruction · **Zarr** chunked array store · **Conservation** total amount preserved when regridding.

## 10. File map (most important)
`ml/pipeline/demo.py` (orchestrator) · `ml/anomaly/detectors.py` · `ml/extraction/regions.py` · `ml/tracking/{tracker,kalman,hindcast}.py` ·
`ml/downscaling/baseline.py` · `ml/physics/*` · `ml/evaluation/metrics.py` · `ml/risk/engine.py` · `ml/impact/geometry.py` · `ml/gnn/graphs.py` · `ml/data/synthetic.py` ·
`data_pipeline/{adapters,validation,storage,ingestion}` · `backend/app/{api/v1,services,core}` · `frontend/src/{pages,features,components,lib,stores}` ·
`database/schema/001_init.sql` · `config/*.yaml` · `docs/science.md`.
