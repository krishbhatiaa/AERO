# Scientific reference (every implemented equation)

Convention for each entry: **What · Input/Output · Mathematics · Units · Assumptions · Reference · Limits · Tests**.
Sample sizes in the demo are tiny; nothing here is a claim of real-world skill.

## 1. Cell area on a sphere — `ml/core/grid.py`
* **Math:** A(φ) = R² · Δλ · (sin φ₂ − sin φ₁), φ₁,₂ = row latitude ∓ Δφ/2; R = 6371.0088 km. Never use pixel counts (a 1° cell at the equator is ~12 300 km², at 60° ~6 200 km²).
* **Units:** km². **Assumes:** spherical Earth (<0.5 % area error). **Tests:** global sum = 4πR²; area shrinks poleward.

## 2. Climatology — `ml/climatology/service.py`
* **What:** distribution of a variable under normal conditions for a time of year. Sample S = {x(t): year(t) ∈ [y₀,y₁], |doy(t) − d| ≤ w (circular)}; mean, std (ddof=1) and 99 quantiles (0.01…0.99) over S at every grid point; quantiles between levels are linearly interpolated.
* **Period/window are parameters** (`config/anomaly.yaml`). Day-of-year uses a non-leap calendar (Feb 29 pools with Feb 28) — a bug found by tests (leap years silently dropped 8 samples).
* **Limits:** stationarity within the period; empirical quantiles (no gamma fit yet); the demo climatology is *invented* (gamma-distributed wet amounts), not real. **Tests:** equals NumPy reference; Dask-lazy equals eager; period/window enforced.

## 3. Detectors — `ml/anomaly/detectors.py`
* **Z-score:** Z = (X − μ)/max(σ, σ_floor). Gaussian assumption — inappropriate for skewed precipitation. Defaults 2 / 3 (documented, uncalibrated).
* **Percentile rank:** piecewise-linear rank between stored quantiles; ties take the upper rank; above the top quantile the rank saturates smoothly: r = L_K + (1−L_K)(1 − e^{−(x−Q_K)/(Q_K−Q_{K−1})}). Defaults P95 / P99.
* **EFI-style:** EFI = (2/π) ∫₀¹ (p − F_f(p)) / √(p(1−p)) dp (Lalaurette 2003). With p = sin²θ: EFI = (4/π) ∫₀^{π/2} (sin²θ − F_f(sin²θ)) dθ, evaluated by the midpoint rule on 64 nodes (exactly ±1 at the extremes because Σ sin² = N/2). F_f(p) = fraction of members below the climatological p-quantile, ties count ½.
  **Not ECMWF's operational EFI** (different climate, resolution, post-processing) and not validated against it. Zero-inflated variables (precipitation in always-dry cells) show a small positive bias because of tie handling; treat |EFI| ≳ 0.5 only in wet regimes. Thresholds 0.5 / 0.8 are a common rule of thumb, not calibrated here.
* **Reference:** Lalaurette, F. (2003) *Early detection of abnormal weather conditions using a probabilistic extreme forecast index*, QJRMS 129, 3037–3057. **Tests:** monotone/bounded rank; EFI → ±1 for extreme ensembles, ≈0 for climate-like ensembles.

## 4. Region extraction — `ml/extraction/regions.py`
Threshold → binary mask → closing (fills 1-cell holes) → connected components (8-connectivity, periodic in longitude for global grids) → properties. Centroid = area-weighted mean of unit vectors (safe across the antimeridian); perimeter = sum of exposed cell edges with true lengths (E–W edges scale with cos φ); confidence = 0.5·sat(peak excess) + 0.3·sat(mean excess) + 0.2·sat(area/5A_min), sat(x)=1−e^{−x}. Small components are counted in diagnostics, not silently dropped. **Tests:** spherical areas, rectangle perimeter, seam merge, 4- vs 8-connectivity.

## 5. Tracking — `ml/tracking/`
* **Association cost:** c = w_d·d/gate + w_o·(1 − IoU(advected previous footprint, candidate)) + w_i·|ΔI|/max(I); Hungarian assignment (`scipy.optimize.linear_sum_assignment`); pairs beyond the gate or `max_cost` are rejected; unmatched tracks coast `max_missed` frames; an unmatched region overlapping a **previous-frame** footprint starts a child track (`parent_id`). Merges are not modelled.
* **Kalman filter:** state [x, y, vₓ, v_y] in a local azimuthal-equidistant plane (km, km/h); white-noise-acceleration process noise Q = σₐ² [[Δt³/3, Δt²/2],[Δt²/2, Δt]]; 95 % position radius = √(5.991·λ_max(P_pos)). Speed/bearing are reported **at the object's own location** (a bug found by tests: bearings in the origin frame were off by the meridian convergence).
* **Hindcast:** re-run the filter on data up to step k, predict k+1…k+H, compare with measured centroids; baseline = persistence. **Limits:** one synthetic track, n≈6 — a mechanics check.

## 6. Downscaling baselines & conservation — `ml/downscaling/baseline.py`, `ml/physics/conservation.py`
* Spline interpolation of order 0/1/3 to the fine-grid centres (edge-clamped; cubic splines have a boundary layer within ~2 coarse cells of the domain edge).
* **Conservation projection (multiplicative):** f′ᵢⱼ = fᵢⱼ · c_I / mean_I(f) (block means equal the coarse value; keeps f ≥ 0). Additive variant: f′ = f + (c_I − mean_I(f)). Idempotent (hypothesis-tested).
* **Assumes:** the coarse value is the area mean of the fine values (true for the synthetic generator; for real products confirm the source's aggregation). Not valid for point-like quantities.

## 7. Physics checks — `ml/physics/`
* **Saturation vapour pressure (Bolton 1980, eq. 10):** eₛ(T) = 6.112·exp(17.67T/(T+243.5)) hPa (T in °C); q_s = 0.622eₛ/(p − 0.378eₛ). Cross-checked against MetPy (agreement within 0.3 %; MetPy uses a different formulation).
* **Horizontal divergence:** ∇·V = (1/(R cos φ)) [∂u/∂λ + ∂(v cos φ)/∂φ] (s⁻¹). Tested on analytic fields (e.g. u = aRΔλ cos φ ⇒ ∇·V = a; uniform v ⇒ −v tan φ / R). It is a **descriptive diagnostic**: near-surface wind is not non-divergent, and a moisture-budget check (P − E = −∇·(qV) − ∂W/∂t) is future work.
* **Non-negativity** and **coarse-cell conservation** are the hard constraints reported per product.
* **Reference:** Bolton, D. (1980) *The computation of equivalent potential temperature*, MWR 108, 1046–1053.

## 8. Synthetic scenario — `ml/data/synthetic.py` (invented, labelled SYNTHETIC)
Holland (1980) pressure profile p(r) = p_c + Δp·exp(−(R_max/r)^B); gradient-wind balance V = √((BΔp/ρ)(R_max/r)^B e^{−(R_max/r)^B} + (rf/2)²) − rf/2 with a 20° inflow angle; Δp = ρ e V_max²/B. Rainfall = eyewall ring + spiral bands + motion asymmetry + orographic enhancement (invented), multiplied on the fine grid by lognormal convective variability; the coarse forecast is the exact block mean of the fine truth; ensemble members perturb track (σ ≈ 15 + 1.8·h km), intensity and size. **It exists to exercise the pipeline with known truth; results on it are not evidence of real skill** (the truth generator is ours).
* **Reference:** Holland, G. J. (1980) *An analytic model of the wind and pressure profiles in hurricanes*, MWR 108, 1212–1218.

## 9. Evaluation metrics — `ml/evaluation/metrics.py`
General: MAE, RMSE, bias, correlation. Extremes: peak error (max pred − max truth), extreme-value bias (mean error where truth ≥ its q-quantile), P95/P99 error, extreme recall/precision (strict `>` when the quantile equals the minimum — zero-inflated fields; a bug found by tests). Spatial: IoU, centroid distance, area error, Chamfer boundary error. Spectral: radially averaged PSD with Hann window; band-power ratio (12–40 km wavelengths; 1 = full recovery). Probabilistic: fair CRPS (Ferro 2014), reliability curve, ECE, interval coverage. Tracking: trajectory/displacement error, continuity, detection rate. Uncertainty on headline numbers: percentile bootstrap **over frames** (not pixels). Blocked-in-time splits are required for learned models (none exist yet).

## 10. Risk engine — `ml/risk/engine.py`, `config/risk.yaml`
s_d = clip((x_d − lo_d)/(hi_d − lo_d), 0, 1); hazard = Σ w_d s_d; score = P^γ · hazard; MODERATE ≥ 0.25, SEVERE ≥ 0.55. Forecast horizon and uncertainty change the **confidence class**, never the category. **All scales/weights/thresholds are demonstration defaults, not calibrated against impacts, and the categories are not official.**

## 11. Uncertainty & impact geometry
Ensemble summaries (mean, median, std, p10/p90/p95/p99, exceedance probability); position envelope = 90th-percentile member distance from the spherical mean position (**not** the NHC cone). Impact/risk/uncertainty polygons: footprint, footprint ⊕ R₆₈, footprint ⊕ R₉₅ with R₆₈ = R₉₅·√(2.279/5.991) (χ² with 2 d.o.f.), buffered in a local azimuthal-equidistant projection; areas in EPSG:6933. PostGIS (`ST_Area(geom::geography)`) and shapely agree to the km² on the demo (seed script cross-check).

## 12. Graphs for GNNs — `ml/gnn/graphs.py`
Icosahedral mesh by recursive midpoint subdivision: V = 10·4ᴸ + 2, E = 30·4ᴸ; edge attributes = [great-circle km, dx, dy in the sender's local tangent frame]; grid↔mesh bipartite k-NN wiring. Model code (encoder–processor–decoder) is **not** implemented.
