"""Append-only JSON-lines audit log for security-relevant actions."""
from __future__ import annotations

import json
import logging
import threading
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from app.core.logging import request_id_var

log = logging.getLogger("app.audit")

AUDIT_EVENT_TYPES = frozenset({
    "auth.success", "auth.failure", "authz.denied",
    "data.ingest", "data.export",
    "model.promote",
    "job.created", "job.completed",
})

_SENSITIVE_KEYS = frozenset({"password", "secret", "token", "api_key", "apikey", "authorization", "credential", "private_key"})


def _redact(data: dict[str, Any]) -> dict[str, Any]:
    result = {}
    for k, v in data.items():
        if any(s in k.lower() for s in _SENSITIVE_KEYS):
            result[k] = "***"
        elif isinstance(v, dict):
            result[k] = _redact(v)
        elif isinstance(v, str) and len(v) > 200:
            result[k] = v[:200] + "..."
        else:
            result[k] = v
    return result


class AuditLogger:
    """Thread-safe appender. In production also ship these records to write-once storage / the ``audit_logs`` table."""

    def __init__(self, path: str | Path, max_bytes: int = 10_000_000, backup_count: int = 5) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._handler: RotatingFileHandler | None = None
        if path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._handler = RotatingFileHandler(str(self.path), maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8")

    def record(self, action: str, actor: str, outcome: str = "ok", **details: Any) -> None:
        if action not in AUDIT_EVENT_TYPES:
            log.debug("non_standard_audit_event", extra={"action": action})
        entry: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "action": action,
            "actor": actor,
            "outcome": outcome,
            "request_id": request_id_var.get(),
            "details": _redact(details),
        }
        line = json.dumps(entry, default=str) + "\n"
        with self._lock:
            if self._handler:
                self._handler.emit(logging.LogRecord("app.audit", logging.INFO, "", 0, line.rstrip(), (), None))
            elif self.path:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.path, "a", encoding="utf-8") as fh:
                    fh.write(line)

    def record_auth(self, principal: str, outcome: str, **details: Any) -> None:
        event = "auth.success" if outcome == "ok" else "auth.failure"
        self.record(event, principal, outcome, **details)

    def record_authz(self, principal: str, **details: Any) -> None:
        self.record("authz.denied", principal, "denied", **details)

    def record_data_event(self, action: str, principal: str, **details: Any) -> None:
        self.record(action, principal, "ok", **details)

    def record_job(self, action: str, principal: str, **details: Any) -> None:
        self.record(action, principal, "ok", **details)

    def read(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]
