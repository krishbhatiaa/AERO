# Backend API image. Build context = repository root.
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PYTHONPATH=/srv:/srv/backend
WORKDIR /srv
# libgomp for numpy/scipy wheels on slim images; libpq for PostgreSQL; netcdf4/pyproj/shapely ship manylinux wheels.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 libpq5 curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install -r requirements.txt psycopg2-binary
COPY ml ./ml
COPY data_pipeline ./data_pipeline
COPY backend ./backend
COPY config ./config
COPY sample_data ./sample_data
RUN useradd --create-home --uid 10001 ewai && mkdir -p /srv/var && chown -R ewai /srv/var
USER ewai
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=30s CMD curl -fsS http://127.0.0.1:8000/api/v1/live || exit 1
CMD ["python", "-m", "uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
