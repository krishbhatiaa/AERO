.PHONY: help install install-frontend test test-py test-web test-db lint typecheck build demo seed-db boundaries dev-backend dev-frontend up down clean zip
PY ?= python3
BACKEND_ENV = PYTHONPATH=..:.

help:            ## list targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-16s %s\n",$$1,$$2}'

install:         ## Python dependencies (dev)
	$(PY) -m pip install -r requirements-dev.txt

install-frontend: ## frontend dependencies
	cd frontend && npm ci --no-audit --no-fund

test: test-py test-web ## everything (PostGIS tests need EWAI_TEST_DATABASE_URL)

test-py:         ## Python tests (ml, data_pipeline, backend)
	$(PY) -m pytest

test-db:         ## PostGIS integration tests (set EWAI_TEST_DATABASE_URL to a scratch *test* database)
	$(PY) -m pytest backend/tests/test_database.py

test-web:        ## frontend unit + accessibility tests
	cd frontend && npx vitest run

typecheck:       ## strict TypeScript
	cd frontend && npx tsc -b --noEmit

lint:            ## ruff (if installed)
	-$(PY) -m ruff check ml data_pipeline backend scripts

build:           ## production frontend build
	cd frontend && npm run build

demo:            ## run the whole chain on the synthetic scenario and print a summary
	$(PY) scripts/run_demo.py

seed-db:         ## load demo products into PostGIS (DATABASE_URL required; apply database/schema/001_init.sql first)
	$(PY) scripts/seed_db.py --database-url "$$DATABASE_URL"

boundaries:      ## rebuild the Natural Earth boundary samples
	$(PY) scripts/build_boundaries.py --src-dir ne_cache && cp sample_data/boundaries/*.geojson frontend/public/data/

dev-backend:     ## API on :8000 (demo mode)
	cd backend && $(BACKEND_ENV) $(PY) -m uvicorn app.main:create_app --factory --reload --port 8000

dev-frontend:    ## dashboard on :5173 (proxies /api to :8000)
	cd frontend && npm run dev

up:              ## docker compose (demo)
	docker compose up --build

down:
	docker compose down

clean:
	rm -rf var frontend/dist .pytest_cache .hypothesis
