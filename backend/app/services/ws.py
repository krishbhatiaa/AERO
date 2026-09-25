"""WebSocket fan-out. Messages: ``{type, ts_utc, request_id, payload}``.

In-process manager (single worker). Multi-worker fan-out via Redis pub/sub is tracked in Batchsize.md.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from app.core.logging import request_id_var
from fastapi import WebSocket

log = logging.getLogger("app.ws")
CHANNELS = ("events", "alerts", "jobs")


def message(type_: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {"type": type_, "ts_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "request_id": request_id_var.get(), "payload": payload}


class ConnectionManager:
    def __init__(self) -> None:
        self._subs: dict[WebSocket, set[str]] = {}
        self.loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self) -> None:
        self.loop = asyncio.get_running_loop()

    async def connect(self, ws: WebSocket, channels: set[str]) -> None:
        self._subs[ws] = channels

    def disconnect(self, ws: WebSocket) -> None:
        self._subs.pop(ws, None)

    @property
    def count(self) -> int:
        return len(self._subs)

    async def broadcast(self, channel: str, type_: str, payload: dict[str, Any]) -> None:
        msg = message(type_, {"channel": channel, **payload})
        for ws, chans in list(self._subs.items()):
            if channel in chans:
                try:
                    await ws.send_json(msg)
                except Exception:  # noqa: BLE001 - a dead socket must not break others
                    self.disconnect(ws)

    def broadcast_threadsafe(self, channel: str, type_: str, payload: dict[str, Any]) -> None:
        """Called from worker threads (job runner)."""
        if self.loop is None or self.loop.is_closed():
            return
        asyncio.run_coroutine_threadsafe(self.broadcast(channel, type_, payload), self.loop)
