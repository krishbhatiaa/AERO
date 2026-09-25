# sample_data/

* `boundaries/` — Natural Earth 1:10m admin-0 / admin-1 clipped to the study window (public domain, https://www.naturalearthdata.com).
  **Not official boundaries** (see `boundaries/NOTICE.md`). Rebuild: `python scripts/build_boundaries.py`.
* `synthetic/` — reserved. The synthetic scenario is generated in-process and deterministically (`ml/data/synthetic.py`, seed in `config/app.yaml`); nothing is stored here.

No real weather observations, reanalysis or forecast data are bundled.
