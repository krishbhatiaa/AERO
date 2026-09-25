# Batchsize.md — what remains, and what else we can do

*(Interpreted as: the remaining work, organised into batches you can schedule, plus extension ideas.)*
Status legend: ✅ implemented & tested · 🟡 partial · ⛔ not started · 🔑 needs real data/access · 🧠 needs GPU + PyTorch · 🧪 research.
Effort: S ≤ 1 day · M 2–4 days · L 1–2 weeks · XL > 2 weeks (one engineer, rough).

---
## 1. Where we stand (honest one-paragraph summary)
The platform, evaluation harness and baselines are real and tested (145 Python + 117 frontend tests, 98 % Python line coverage; PostGIS verified; 0 axe violations). The **AI models are
not**: no GNN, U-Net or diffusion model exists, nothing was trained, and no result has been validated on real weather data. Everything shown in the demo is
synthetic and labelled so. The fastest route to a credible research result is **Batch 2 (real data) → Batch 3 (models)**; Batch 1 makes it production-shaped.

---
## 2. Blueprint phase status (your 24 phases)

| # | Phase | Status | Notes |
|---|---|---|---|
| 1 | Repo + Docker + config | 🟡 | Repo/config ✅. Dockerfiles + compose written, **never executed** (no Docker here); `worker`/`ml-service` containers not written |
| 2 | PostGIS + Redis + MinIO | 🟡 | PostGIS schema applied & tested ✅; Redis cache ✅; S3/MinIO provider ✅ (moto-tested); API does not persist to DB yet |
| 3 | Ingestion framework | ✅ | |
| 4 | ERA5 sample pipeline | 🟡🔑 | request builder + adapter ✅; live download untested (needs your CDS token) |
| 5 | Xarray/Dask preprocessing | 🟡 | canonicalisation/units/lon ✅; **missing:** regridding service, temporal alignment, normalisation statistics |
| 6 | Climatology | ✅ | gamma fit for precipitation ⛔ |
| 7 | Anomaly baseline | ✅ | learned detector = wrapper only 🧠 |
| 8 | Event extraction | ✅ | |
| 9 | Tracking | ✅ | merges & graph association ⛔ |
| 10 | FastAPI | ✅ | `POST /uploads`, JWT, Prometheus ⛔ |
| 11 | React dashboard | ✅ | |
| 12 | Interactive map | 🟡 | custom canvas/SVG map (offline, no tile server). **MapLibre/deck.gl, 12 km/5 km grid overlays, global view, isobars ⛔** |
| 13 | Baseline downscaling | ✅ | |
| 14 | CNN / U-Net | ⛔🧠 | |
| 15 | GNN tracking | 🟡🧠 | graph builders incl. icosahedral mesh ✅; model/training ⛔ |
| 16 | Conditional diffusion | ⛔🧠 | |
| 17 | Physics-informed loss | 🟡🧠 | checks ✅, NumPy reference losses ✅, autograd ports ⛔ |
| 18 | Uncertainty | 🟡 | ensemble ✅; diffusion samples, conformal intervals, calibration ⛔ |
| 19 | Alert engine | 🟡 | alerts + GeoJSON ✅; CAP-IN XML, dissemination ⛔ |
| 20 | 3D globe | ⛔🧪 | |
| 21 | Testing | 🟡 | unit/integration/a11y ✅; automated Playwright E2E ⛔ (manual screenshots only) |
| 22 | Performance | 🟡 | lazy/chunked design ✅; no benchmarks/budgets measured |
| 23 | Security hardening | 🟡 | see §5; no external pen-test, no dependency audit run |
| 24 | Production deployment | ⛔ | docs only |

---
## 3. Batches (recommended order)

### Batch 1 — Production-shape the platform (no GPU, no external data) · ~2 weeks
| ID | Item | Why | Done when | Effort |
|---|---|---|---|---|
| P1 | SQLAlchemy 2 (async) + GeoAlchemy2 models, **Alembic** migration mirroring `001_init.sql`, `PostgresProductStore` behind the existing store interface | API currently serves memory; persistence is a spec item | API tests run against both stores; testcontainers PostGIS in CI | L |
| P2 | Celery + Redis worker (`worker` compose service); job cancel/retry; keep the job model | in-process thread pool is not scalable | jobs survive API restarts; WS progress unchanged | M |
| P3 | Redis-backed rate limiter + WebSocket pub/sub fan-out | multi-worker correctness | 2 API replicas share limits/events | M |
| P4 | JWT (short-lived) + `users` table use; `POST /uploads` with magic-byte allow-list, size cap, subprocess parsing, server-generated keys | spec §48 | upload tests incl. traversal/zip-bomb cases | M |
| P5 | `/metrics` (Prometheus), OpenTelemetry hooks, Sentry hook | observability | dashboards for latency/jobs | S |
| P6 | Alert dissemination (email/webhook) with throttling; **CAP-IN export** once the official profile is obtained; Hindi/regional-language alert text (expert-reviewed) | localized alerts | XML validates against the official schema | M |
| F1 | Map: 12 km / 5 km grid overlays, MSLP isobars (marching squares in a Web Worker), global view, optional MapLibre + deck.gl renderer | spec §42, §71 | 60 fps pan/zoom on the demo domain; overlays match `GridSpec` | L |
| F2 | Playwright E2E (demo path) + visual regression + axe in CI | spec §53 | CI fails on regressions | M |
| O1 | **Build and run the Docker images**, fix what breaks; `npm`/`pip` lockfile audit (`pip-audit`, `npm audit`, trivy, gitleaks) | never executed | `docker compose up` reaches a working dashboard | S–M |
| S1 | Regridding service (conservative/bilinear, Dask-lazy), temporal alignment, normalisation stats with recorded config hash | spec §14 | property tests: round-trip and conservation | M |

### Batch 2 — Make it real (needs data access, no GPU) · ~2–3 weeks 🔑
| ID | Item | Done when |
|---|---|---|
| D1 | **ERA5 runner**: download → ingest → 1991–2020 climatology → anomaly → tracking for a real event (proposal: TC *Tauktae*, May 2021) | run reproducible from a manifest; provenance labels REANALYSIS |
| D2 | **IBTrACS** comparison: track error / displacement error / continuity vs best track, with bootstrap CIs | table + chart in the Evaluation page (real, not synthetic) |
| D3 | **IMDAA** adapter filled from real files (12 km-class); India climatology; **IMD gridded rainfall** validation of totals | `variable_map` populated; validation report |
| D4 | `REAL_DATA_MODE` pipeline runner (today it only *reports* source availability and falls back to SYNTHETIC) | UI shows REANALYSIS/FORECAST labels; explicit fallback banner |
| D5 | Official / Survey-of-India-compliant boundaries; **district-level** intersections in PostGIS | legal review recorded in `boundary_source` |
| D6 | Gamma-fit precipitation climatology; calibrate detector thresholds against **IMD rainfall categories** (verify current IMD definitions); validate EFI-style implementation against published ECMWF examples | calibration notebook + documented thresholds |
| D7 | NEPS-G / NCUM adapters filled **only** through authorised NCMRWF access | 🔑 requires NCMRWF |

### Batch 3 — Learned models (needs GPU + real pairs) · ~4–8 weeks 🧠
Prerequisite: real fine-resolution truth for at least precipitation (proposal: ERA5 → CHIRPS 0.05° pairs; NCMRWF high-resolution runs if available) and IBTrACS labels.
| ID | Item | Promotion gate |
|---|---|---|
| M1 | Residual CNN + **U-Net** downscaler (terrain, land-sea mask, event context); PyTorch ports of ExtremeWeighted/Quantile/Huber losses **tested against `ml/losses/reference.py`** | beats `bicubic_conservative` on peak error, P99 error and PSD ratio with bootstrap CI excluding 0, on a time-blocked held-out set |
| M2 | **Conditional residual diffusion** (EDM-style, few-step sampler, N samples → mean/median/P90/P95/P99/exceedance) | vs U-Net on extremes + power spectrum + fair CRPS; **report whichever wins per metric** |
| M3 | **GNN tracker**: Tier 1 learned association, Tier 2 encoder–processor–decoder on the icosahedral mesh; GRU vs temporal Transformer by benchmark | beats Hungarian+Kalman on track continuity/displacement error on IBTrACS-labelled events |
| M4 | Physics-informed loss module (soft/hard conservation, saturation bound) + ablations | ablation table showing effect on extremes and conservation |
| M5 | Split-conformal track envelopes; reliability diagrams; coverage tests | empirical coverage within ±3 % of nominal on held-out events |
| M6 | MLflow registry + model cards + promotion automation; safetensors checkpoints with SHA-256 in the registry | `experimental → candidate → recommended` enforced by CI |
| M7 | Learned anomaly detector with **independent** labels (IMD event catalogue) — with percentile-derived labels it can only imitate the baseline | beats percentile detector on event-level F1 |

### Batch 4 — Extensions & research 🧪
Heatwave / cold-wave detectors (T2m anomaly + duration criteria; mostly config + risk scales) · high-wind events · track merges & ensemble track clustering ·
rapid-intensification indicator · moisture-budget diagnostic (P − E = −∇·(qV) − ∂W/∂t) · GraphCast-style mesh forecast model · 3D globe (React-Three-Fiber: rotating
globe, anomaly texture, instanced intensity columns, uncertainty cone, GPU particles, automatic degradation, 2D fallback) · OGC API / COG tiles (TiTiler) and Zarr pyramids ·
verification dashboards (reliability, ROC, rank histograms) · HPC/Slurm batch packaging for NCMRWF infrastructure · DVC for dataset versioning.

---
## 4. What else can we do (ideas by value ÷ effort)
1. **Heatwave & cold-wave in one day of work** — the platform is variable-agnostic: add `t2m` scales to `config/risk.yaml`, two-sided z-score, duration filter. Big demo value.
2. **Validation page with real numbers** (after D1–D2) — nothing convinces judges like an honest real-event table with confidence intervals.
3. **"What-if" explorer**: sliders for thresholds (P95→P99, min area) showing live effect on events/alerts — explains the configuration story.
4. **Ensemble track clustering** (e.g. landfall groups) — turns spread into scenarios forecasters can reason about.
5. **Alert quality-of-service**: throttling, de-duplication, update/cancel semantics, multilingual text, audit trail (all data models exist).
6. **Progressive Web App** for field officers: cached last alert, offline map, low-bandwidth mode.
7. **Explainability**: per-alert contribution bars from the risk engine (already returns components); counterfactual "what would make this MODERATE?".
8. **Nowcasting fusion** (radar/satellite) for the first 6 h — a separate module feeding the same tracker.
9. **Uncertainty communication study**: test the envelope/confidence visuals with real forecasters before finalising the design.
10. **Presentation assets** for SIH: 90-second screen-recorded demo following `docs/demo.md`, architecture poster, one-page limitations sheet.

---
## 5. Known limitations and risks
* **No real-data validation.** All metrics are on a synthetic scenario whose truth we generate; conclusions about real skill are not supported.
* **Synthetic circularity:** a learned model that "wins" on our generator proves little; real pairs are mandatory (M1 gate).
* **ERA5 is ~28 km**, not 12 km; no free 5 km truth exists for most variables (see D1/M1 prerequisites).
* **Risk categories are uncalibrated** and unofficial; thresholds are demonstration defaults (`config/*.yaml`).
* **EFI-style ≠ ECMWF EFI**; zero-inflated variables have a small tie-handling bias.
* **Tracking:** one synthetic track (n≈6 hindcast samples); merges not modelled; centroid of a rain shield ≠ storm centre.
* **Boundaries:** Natural Earth, not official; district level missing.
* **Persistence:** API state is in memory (lost on restart) until P1.
* **Security:** in-process rate limiter; API keys in memory in the browser (by design) but no SSO; no external penetration test; `AUTH_MODE=none` is dev-only.
* **Docker/CI/CDS/S3-on-real-AWS** paths were written but **not executed** here.
* **Frontend:** custom map (no tiles, no global view); animation timeline limited to the 48 h of the synthetic run; only Chromium was used for visual checks.
* **Licence** in the repo is a placeholder (MIT) — confirm with the project owners and with data providers.

## 6. First things to verify on your machine
1. `make install install-frontend && make test` (expect 141 + 117 passing; 4 PostGIS tests skipped without `EWAI_TEST_DATABASE_URL`).
2. `make demo`, then run the dashboard and press PLAY.
3. `docker compose up --build` — fix anything that fails (O1).
4. `python scripts/download_era5.py ... --dry-run`, then a real download with your CDS token.
5. Apply `database/schema/001_init.sql` to a scratch PostGIS and run `make test-db`.

## 7. Spec-compliance matrix (your 84 requirements, grouped)
| Spec § | Requirement | Status |
|---|---|---|
| 0, 80 | No fake science; labelled data kinds | ✅ (enforced by types, UI badges, tests) |
| 1–3 | End-to-end chain, layered architecture | ✅ chain (baselines) · 🟡 data layer (PostGIS not wired) |
| 4–6 | Stack: FastAPI, Pydantic v2, Xarray/Dask/NumPy/SciPy/Shapely/PyProj | ✅ · SQLAlchemy/Alembic/Celery ⛔ · PyTorch/PyG/Diffusers/GeoPandas/Cartopy/Rasterio ⛔ (not needed yet) · MapLibre/deck.gl ⛔ (custom map) |
| 7–9 | DB tables/indexes, object-storage abstraction, Redis | ✅ DDL+indexes verified · ✅ Local+S3 · 🟡 Redis = cache only |
| 10–12 | Adapters, ingestion pipeline, validation | ✅ (restricted sources 🔑) |
| 13–15 | Canonical model, preprocessing, climatology | ✅ · 🟡 preprocessing (see S1) · ✅ climatology |
| 16–19 | Detectors, masks, extraction, tracking | ✅ (graph association ⛔) |
| 20–22 | GNN, temporal model, outputs | 🟡 graph abstraction only · model ⛔🧠 |
| 23–25 | Downscaling baselines → CNN/U-Net → diffusion | ✅ baselines · ⛔🧠 rest |
| 26–27 | Physics-informed & extreme-aware losses | 🟡 references + checks · ports ⛔🧠 |
| 28–29 | Evaluation & baseline comparison | ✅ metrics · 🟡 comparison (baselines only) |
| 30 | Uncertainty | 🟡 |
| 31–33 | Risk, impact, alerts | ✅ · ✅ · 🟡 |
| 34–35 | REST API, WebSocket | ✅ |
| 36–45 | Frontend design, dashboard, 3D, controls, time machine, map, comparison, explainability, provenance | ✅ except 3D ⛔, grid overlays/global ⛔, MapLibre ⛔ |
| 46–47 | Model registry, experiment management | 🟡 registry (baselines) · experiments ⛔ (nothing trained) |
| 48, 70 | Security | ✅ core controls · JWT/uploads ⛔ |
| 49 | Accessibility WCAG 2.2 AA | ✅ tested (axe + contrast) |
| 50–52 | Time, errors, observability | ✅ · ✅ · 🟡 (no Prometheus) |
| 53 | Testing | ✅ unit/integration/frontend/a11y · ⛔ automated E2E |
| 54–56 | Synthetic engine, demo mode, real-data mode | ✅ · ✅ · 🟡 (reports only) |
| 57–59 | Data docs, config, Docker | ✅ · ✅ · 🟡 (unexecuted; no worker/ml-service) |
| 60–63 | Structure, docs, code quality | ✅ (docs: README, understanding, science, data, demo, API; a standalone data dictionary and per-model cards ⛔) |
| 66 | 24-phase order | see §2 |
| 67–69 | Performance, GPU detection, DB indexing | 🟡 · ✅ (reports CPU/CUDA) · ✅ |
| 71–79 | Frontend performance, animation, pages, 5 km page, alerts, fundamentals, demo scenario | ✅ (Web Workers ⛔) |
| 82–83 | Quality gate & self-audit | see below |

## 8. Final self-audit (condensed)
| Audit | Verdict |
|---|---|
| Architecture | Layered, ports-and-adapters; modular monolith; in-memory persistence is the main gap |
| Security | Solid baseline controls, tested; JWT/uploads/pen-test/dependency audit outstanding |
| Data | Validation exhaustive for the listed failure classes; no real data exercised |
| ML | Baselines correct and measured; **no learned models** |
| Scientific validity | Equations documented with units/assumptions/references/tests; synthetic circularity explicitly disclosed |
| Database | DDL verified on PostGIS 16/3.4 incl. GIST + append-only audit; no ORM/migrations |
| API | Consistent envelopes/errors, pagination, filters, auth hooks, rate limits; OpenAPI generated |
| Frontend | Strict TS, 117 tests, six async states, 0 axe violations; custom map limits |
| Accessibility | WCAG 2.2 AA automated checks pass; no manual screen-reader test performed |
| Performance | Designed for lazy/chunked data; not benchmarked at scale |
| Test coverage | 145 Python (incl. 4 PostGIS) + 117 frontend; Python line coverage 98 % (pytest-cov); frontend coverage not measured |
| Known limitations | §5 |
| Future improvements | §3–4 |
