"""Dependency health checks (TCP reachability for external services; never exposes URLs or credentials)."""
from __future__ import annotations

import importlib.util
import socket
from typing import Any
from urllib.parse import urlparse

from app.core.config import Settings

from data_pipeline.storage.base import StorageProvider


def _tcp(url: str, default_port: int) -> tuple[bool, str]:
    try:
        u = urlparse(url)
        with socket.create_connection((u.hostname or "localhost", u.port or default_port), timeout=1.0):
            return True, "reachable (TCP)"
    except OSError:
        return False, "unreachable"


def device_info(settings: Settings) -> dict[str, Any]:
    if importlib.util.find_spec("torch") is None:
        return {"requested": settings.ml_device, "resolved": "cpu", "cuda_available": False,
                "detail": "PyTorch is not installed: CPU baselines only (no learned models are used)"}
    import torch

    cuda = bool(torch.cuda.is_available())
    resolved = "cuda" if settings.ml_device in ("auto", "cuda") and cuda else "cpu"
    return {"requested": settings.ml_device, "resolved": resolved, "cuda_available": cuda,
            "detail": "CUDA unavailable: CPU fallback" if settings.ml_device == "cuda" and not cuda else "ok"}


def check_dependencies(settings: Settings, storage: StorageProvider, store_ready: bool, ws_count: int, cache_name: str) -> dict[str, Any]:
    deps: dict[str, dict[str, Any]] = {}
    ok_storage, msg = storage.healthcheck()
    deps["storage"] = {"status": "ok" if ok_storage else "down", "backend": storage.name, "detail": msg}
    if settings.database_url:
        ok, msg = _tcp(settings.database_url, 5432)
        deps["database"] = {"status": "ok" if ok else "down", "detail": msg + "; not yet used for persistence"}
    else:
        deps["database"] = {"status": "not_configured", "detail": "DATABASE_URL not set (in-memory store in use)"}
    if settings.redis_url:
        ok, msg = _tcp(settings.redis_url, 6379)
        deps["redis"] = {"status": "ok" if ok else "down", "detail": msg, "cache": cache_name}
    else:
        deps["redis"] = {"status": "not_configured", "detail": "REDIS_URL not set", "cache": cache_name}
    deps["products"] = {"status": "ok" if store_ready else "down", "detail": "pipeline products loaded" if store_ready else "no pipeline run has completed"}
    deps["ml_device"] = {"status": "ok", **device_info(settings)}
    deps["websocket"] = {"status": "ok", "connections": ws_count}
    ready = all(d["status"] in ("ok", "not_configured") for d in deps.values())
    return {"ready": ready, "dependencies": deps}
