# QUICKSTART

Everything below works **without any external data**: demo mode uses the built-in synthetic scenario.
Requirements: Python 3.12+, Node 22+, (optional) Docker, (optional) PostgreSQL 16 + PostGIS 3.

## 1. Clone and install
```bash
git clone <your-fork> extreme-weather-ai && cd extreme-weather-ai
python3 -m pip install -r requirements-dev.txt        # or: make install
cd frontend && npm ci --no-audit --no-fund && cd ..   # or: make install-frontend
```

## 2. Configure
```bash
cp .env.example .env        # defaults run the demo locally; edit only what you need. Never commit .env
```

## 3. Run the pipeline once (no server)
```bash
python scripts/run_demo.py                 # prints event, tracking, alert and downscaling-baseline metrics
python scripts/load_sample_data.py         # optional: ingest the synthetic sample -> validated Zarr + job record in ./var/data
```

## 4. Run the API and dashboard
```bash
# terminal 1
cd backend && PYTHONPATH=..:. python -m uvicorn app.main:create_app --factory --reload --port 8000
# terminal 2
cd frontend && npm run dev                 # http://localhost:5173  (proxies /api and the WebSocket to :8000)
```
Open **http://localhost:5173**. API docs: http://localhost:8000/api/v1/docs · health: `/api/v1/health`, `/api/v1/ready`, `/api/v1/live`.

## 5. Run the demo (2 minutes)
1. **Mission Control** — press **PLAY FORECAST** (T+00 → T+48). The divider follows the event: left = coarse forecast, right = baseline 5 km-class interpolation.
2. Switch tools (Pan / **Probe** / **Measure**), toggle layers, try **SINGLE** mode and the synthetic-truth source.
3. Right panels: *Why this event?*, ensemble spread, measured downscaling baselines, physics checks, alert with **Export GeoJSON**, provenance.
4. **Events → detail**: charts (each has a *Table* view), 12 km-class vs 5 km-class vs truth.
5. **Evaluation**: baseline metrics with bootstrap CIs. **Models & Pipeline**: honest status of each stage. **System → Run pipeline**: launches an async job; progress streams over the WebSocket.

## 6. Tests
```bash
make test-py           # 141 Python tests
make test-web          # 117 frontend tests (incl. axe accessibility + WCAG contrast of the tokens)
make typecheck         # strict TypeScript
```

## 7. Optional: PostgreSQL/PostGIS
```bash
createdb ewai && psql ewai -v ON_ERROR_STOP=1 -f database/schema/001_init.sql
python scripts/seed_db.py --database-url postgresql://user:password@localhost:5432/ewai   # loads demo products, cross-checks PostGIS vs shapely
# PostGIS integration tests (drops/recreates the public schema of a scratch *test* database!):
EWAI_TEST_DATABASE_URL=postgresql://user:password@localhost:5432/ewai_test make test-db
```
The API still serves from memory; DB-backed repositories are on the roadmap (`Batchsize.md`).

## 8. Optional: Docker (written, not yet executed by the authors)
```bash
docker compose up --build                  # backend :8000 + dashboard :8080 (demo mode)
docker compose --profile data up --build   # + PostGIS, Redis, MinIO (set REDIS_URL / DATABASE_URL / STORAGE_BACKEND in .env to use them)
```
If a build fails, please open an issue with the log — this is the least-verified part of the repo.

## 9. Real data
See `docs/data_acquisition.md` (ERA5 with your own CDS token; IMDAA/IMD/NCMRWF only with legitimate access). `REAL_DATA_MODE=true` currently *reports* source availability and explicitly falls back to SYNTHETIC; the real-data pipeline runner is future work.

## Troubleshooting
| Symptom | Fix |
|---|---|
| `/api/v1/ready` = 503 | Read the per-dependency report in the response; unreachable `DATABASE_URL`/`REDIS_URL` make readiness fail by design. Unset them for demo mode. |
| Dashboard shows *Offline* | Backend not running / wrong `VITE_PROXY_TARGET`. It recovers automatically once the API is up. |
| 401 responses | `AUTH_MODE=api_key`: click the key icon in the header and paste your key (kept in memory only). |
| Startup takes a few seconds | The demo pipeline runs at boot (~5 s on 1 CPU). |
