# Demo & presentation guide (for judges)

## The 60-second story
1. "Given a forecast, find extreme events, follow them through time, sharpen them to 5 km-class detail, check physics, state uncertainty, and turn it into a localized alert."
2. Open **Mission Control**, press **PLAY FORECAST**. Point out: anomaly footprint, Kalman track, uncertainty envelope, impact/risk polygons, the **12↔5 km wipe** following the storm.
3. Open **Evaluation**: "Every interpolation baseline under-predicts the peak. That measured gap is what a learned downscaler must beat — we report it *before* claiming anything."
4. Open **Models & Pipeline**: "Every stage shows what actually runs and what is planned. No model has been trained."

## Say this, not that
| Say | Don't say |
|---|---|
| "Synthetic scenario with known truth, to test the pipeline end-to-end." | "Our AI predicts cyclones." |
| "Baselines are implemented and measured; learned models are next and must beat them." | "The diffusion model preserves 97 % of peaks." (no such model exists) |
| "Severity is an analytical category; official warnings come from IMD." | "This is a warning system." |
| "Designed for NEPS-G/IMDAA; adapters report ACCESS REQUIRED until authorised data is provided." | "It runs on NEPS-G data." |

## Demonstrable claims (all reproducible with `make demo` / the tests)
* Ingestion rejects bad data and records why (quarantine record, never deletes).
* Extremes are smoothed by interpolation: peak error −10 to −34 mm/6h vs synthetic truth; conservation removes block-mean bias.
* Kalman extrapolation beats persistence on the synthetic track (25 vs 88 km at +6 h, n=6 — mechanics check).
* PostGIS and shapely agree on region intersection areas.
* The UI is keyboard-operable, WCAG-2.2-AA-checked (axe: 0 violations on every page, light and dark), labels every layer with its data kind and every time with its zone.

## Questions judges may ask
* *"Where is the AI?"* — Honest answer: the platform, evaluation harness, graph mesh and baselines are done; GNN/U-Net/diffusion training needs a GPU and real fine-resolution pairs (see `Batchsize.md`, phases M1–M4). We did not fake it.
* *"Why not ERA5 for 12 km?"* — ERA5 is ~25–30 km. The grid is metadata, so the same code runs on IMDAA/NEPS-G once access is granted.
* *"How do you know 5 km is right?"* — We don't yet: no free 5 km truth for most variables. Plan: CHIRPS pairs for precipitation, then NCMRWF high-resolution runs if available.
