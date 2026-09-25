"""Secrets management with environment and file-based sources."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from threading import Lock
from typing import Any

log = logging.getLogger("app.secrets")

_file_cache: dict[str, str] = {}
_file_lock = Lock()
_redacted = {"***"}


def _read_secret_file(name: str, file_path: str) -> str | None:
    cache_key = f"{name}:{file_path}"
    with _file_lock:
        if cache_key in _file_cache:
            return _file_cache[cache_key]
    try:
        path = Path(file_path)
        if not path.is_file():
            return None
        value = path.read_text(encoding="utf-8").strip()
        if not value:
            return None
        with _file_lock:
            _file_cache[cache_key] = value
        return value
    except Exception:
        log.warning("secret_file_read_failed", extra={"name": name})
        return None


def get_secret(name: str) -> str | None:
    env_val = os.environ.get(name)
    if env_val:
        return env_val
    file_val = os.environ.get(f"{name}_FILE")
    if file_val:
        return _read_secret_file(name, file_val)
    return None


def get_secret_required(name: str) -> str:
    val = get_secret(name)
    if val is None:
        raise ValueError(f"Required secret '{name}' is not set")
    return val


def redact_secret(value: str | None) -> str:
    if value is None:
        return "<not-set>"
    return "***"


def redact_from_dict(data: dict[str, Any], keys: set[str] | None = None) -> dict[str, Any]:
    if keys is None:
        keys = {"password", "secret", "token", "api_key", "apikey", "authorization", "credential", "private_key"}
    result = {}
    for k, v in data.items():
        if any(sensitive in k.lower() for sensitive in keys):
            result[k] = redact_secret(str(v) if v else None)
        elif isinstance(v, dict):
            result[k] = redact_from_dict(v, keys)
        else:
            result[k] = v
    return result
