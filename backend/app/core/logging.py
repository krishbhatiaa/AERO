"""Structured JSON logging with request/job correlation ids carried in context variables."""
from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
job_id_var: ContextVar[str] = ContextVar("job_id", default="-")

_STD = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    """One JSON object per line; extra fields are included, exceptions are logged as type + message only."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_var.get(),
            "job_id": job_id_var.get(),
        }
        payload.update({k: v for k, v in record.__dict__.items() if k not in _STD and not k.startswith("_")})
        if record.exc_info and record.exc_info[0] is not None:
            payload["exc_type"] = record.exc_info[0].__name__
        return json.dumps(payload, default=str)


class TextFormatter(logging.Formatter):
    """Human-readable text format for development."""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        rid = request_id_var.get()
        jid = job_id_var.get()
        parts = [ts, record.levelname.ljust(8), record.name, f"[rid={rid} jid={jid}]", record.getMessage()]
        if record.exc_info and record.exc_info[0] is not None:
            parts.append(f"exc={record.exc_info[0].__name__}")
        return " ".join(parts)


def configure_logging(level: str = "INFO", fmt: str = "json", log_file: str = "") -> None:
    root = logging.getLogger()
    root.handlers.clear()
    formatter = JsonFormatter() if fmt == "json" else TextFormatter()
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    root.addHandler(handler)
    if log_file:
        from logging.handlers import RotatingFileHandler
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(str(path), maxBytes=10_000_000, backupCount=5, encoding="utf-8")
        file_handler.setFormatter(JsonFormatter())
        root.addHandler(file_handler)
    root.setLevel(level.upper())
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
