"""FastAPI application factory."""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from app.api.v1 import alerts, catalog, events, forecasts, health, jobs, mode, uploads, ws
from app.core.audit import AuditLogger
from app.core.cache import create_cache
from app.core.config import API_PREFIX, APP_VERSION, Settings, get_settings
from app.core.errors import install_error_handlers
from app.core.metrics import metrics_collector
from app.core.logging import configure_logging, request_id_var
from app.core.security import (
    SECURITY_HEADERS,
    BodyLimitMiddleware,
    ConcurrencyLimitMiddleware,
    RateLimiter,
    RateLimitMiddleware,
    RequestTimeoutMiddleware,
)
from app.services.jobs import JobManager
from app.services.store import ProductStore
from app.services.ws import ConnectionManager
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from data_pipeline.adapters.registry import all_descriptors
from data_pipeline.storage.factory import storage_from_env
from ml.pipeline.real import RealResult, run_real_pipeline

log = logging.getLogger("app")
_SAFE_REQUEST_ID = 64


class RequestContextMiddleware:
    """Assigns/propagates ``X-Request-ID``, adds security headers and emits one structured access log line."""

    def __init__(self, app: ASGIApp, hsts: bool) -> None:
        self.app, self.hsts = app, hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        raw = dict(scope.get("headers") or []).get(b"x-request-id", b"").decode("latin-1")
        rid = raw if raw and len(raw) <= _SAFE_REQUEST_ID and raw.replace("-", "").replace("_", "").isalnum() else uuid.uuid4().hex
        token = request_id_var.set(rid)
        started = time.perf_counter()
        status = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = list(message.get("headers", []))
                extra = {"X-Request-ID": rid, **SECURITY_HEADERS}
                if self.hsts:
                    extra["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
                if scope["path"].startswith(API_PREFIX) and status < 400 and b"cache-control" not in {k.lower() for k, _ in headers}:
                    extra["Cache-Control"] = "no-store"
                headers += [(k.lower().encode(), v.encode()) for k, v in extra.items() if k.lower().encode() not in {h[0].lower() for h in headers}]
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            dur = time.perf_counter() - started
            metrics_collector.record_request(scope["method"], scope["path"], status, dur)
            log.info("request", extra={"method": scope["method"], "path": scope["path"], "status": status,
                                       "ms": round(dur * 1000, 1)})
            request_id_var.reset(token)


def create_app(settings: Settings | None = None, preloaded: RealResult | None = None) -> FastAPI:
    """Build the application. ``preloaded`` lets tests inject a pipeline result instead of recomputing it."""
    get_settings.cache_clear()
    s = settings or get_settings()
    configure_logging(s.log_level, fmt=s.log_format, log_file=s.log_file)

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # noqa: ANN202
        app.state.ws.bind_loop()
        log.info("startup mode", extra={"data_mode": s.data_mode, "env": s.env, "demo_mode": s.demo_mode, "real_data_mode": s.real_data_mode})
        if preloaded is not None:
            app.state.store = ProductStore(preloaded)
        elif s.data_mode == "real":
            available = all_descriptors(data_root=s.data_path)
            real_sources = [d for d in available if d.status.value in ("AVAILABLE", "DOWNLOADABLE") and d.name != "SYNTHETIC"]
            if not real_sources:
                log.warning("REAL_DATA_MODE active but no real data sources; auto-generating sample ERA5 data")
                try:
                    from scripts.generate_sample_era5 import generate_era5_sample
                    generate_era5_sample()
                    result = await asyncio.to_thread(run_real_pipeline)
                    app.state.store = ProductStore(result)
                    log.info("Real data pipeline ready with auto-generated ERA5 sample")
                except Exception:
                    log.warning("ERA5 sample generation failed; falling back to demo pipeline", exc_info=True)
                    from ml.pipeline.demo import run_demo_pipeline
                    result = await asyncio.to_thread(run_demo_pipeline)
                    app.state.store = ProductStore(result)
                    log.info("Demo pipeline ready (fallback)")
            else:
                log.info("real data mode active", extra={"available_sources": [d.name for d in real_sources]})
                try:
                    result = await asyncio.to_thread(run_real_pipeline)
                    app.state.store = ProductStore(result)
                    log.info("Real data pipeline ready")
                except Exception:
                    log.error("Real pipeline failed; falling back to demo", exc_info=True)
                    from ml.pipeline.demo import run_demo_pipeline
                    result = await asyncio.to_thread(run_demo_pipeline)
                    app.state.store = ProductStore(result)
        elif s.demo_mode:
            try:
                from ml.pipeline.demo import run_demo_pipeline
                result = await asyncio.to_thread(run_demo_pipeline)
                app.state.store = ProductStore(result)
                log.info("demo data pipeline ready")
            except Exception:  # noqa: BLE001 - keep serving health endpoints; /ready reports the problem
                log.error("real data pipeline failed at startup", exc_info=True)
        yield
        app.state.jobs.shutdown()

    app = FastAPI(title="Extreme Weather Intelligence API", version=APP_VERSION, lifespan=lifespan,
                  docs_url=f"{API_PREFIX}/docs", redoc_url=None, openapi_url=f"{API_PREFIX}/openapi.json",
                  description="Decision-support API for spatio-temporal tracking of extreme weather anomalies. "
                              "Not an official warning service. Products derived from ERA5 reanalysis data.")
    ws_manager = ConnectionManager()
    Path(s.data_path).mkdir(parents=True, exist_ok=True)
    app.state.settings = s
    app.state.storage = storage_from_env({"STORAGE_BACKEND": s.storage_backend, "DATA_PATH": s.data_path, "S3_BUCKET": s.s3_bucket,
                                          "S3_ENDPOINT": s.s3_endpoint, "S3_REGION": s.s3_region,
                                          "AWS_ACCESS_KEY_ID": s.aws_access_key_id.get_secret_value(),
                                          "AWS_SECRET_ACCESS_KEY": s.aws_secret_access_key.get_secret_value()})
    app.state.cache = create_cache(s.redis_url)
    app.state.audit = AuditLogger(s.audit_log_path)
    app.state.ws = ws_manager
    app.state.jobs = JobManager(on_event=ws_manager.broadcast_threadsafe)
    app.state.store = None
    app.state.started_at = time.time()

    install_error_handlers(app)
    app.add_middleware(BodyLimitMiddleware, max_bytes=s.max_body_bytes)
    app.add_middleware(ConcurrencyLimitMiddleware, max_concurrent=s.max_concurrent_jobs)
    app.add_middleware(RequestTimeoutMiddleware, timeout=s.request_timeout_seconds)
    app.add_middleware(RateLimitMiddleware, limiter=RateLimiter(s.rate_limit_per_minute))
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origin_list, allow_methods=["GET", "POST", "OPTIONS"],
                       allow_headers=["Content-Type", "X-API-Key", "X-Request-ID", "Authorization"],
                       expose_headers=["X-Request-ID", "Retry-After", "Location"],
                       max_age=600)
    app.add_middleware(RequestContextMiddleware, hsts=s.hsts_enabled or s.env == "production")

    for r in (health.router, events.router, forecasts.router, alerts.router, jobs.router, catalog.router, mode.router, uploads.router, ws.router):
        app.include_router(r, prefix=API_PREFIX)

    @app.get("/metrics", tags=["observability"])
    @app.get(f"{API_PREFIX}/metrics", tags=["observability"])
    async def get_prometheus_metrics() -> Response:
        """Prometheus metrics scraper endpoint."""
        body = metrics_collector.generate_metrics_text(app.state)
        return Response(content=body, media_type="text/plain; version=0.0.4")

    return app


app = create_app()
