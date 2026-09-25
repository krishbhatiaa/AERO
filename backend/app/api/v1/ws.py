"""WebSocket endpoint for live dashboard updates (events, alerts, jobs)."""
from __future__ import annotations

import asyncio
from typing import Any

from app.core.security import authenticate_key
from app.services.ws import CHANNELS, message
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, channels: str = "events,alerts,jobs") -> None:
    """Query ``channels`` selects subscriptions. With ``AUTH_MODE=api_key`` the first client message must be
    ``{"type": "auth", "api_key": "..."}`` (keys are never put in the URL)."""
    st = ws.app.state
    await ws.accept()
    if st.settings.auth_mode != "none":
        try:
            first: dict[str, Any] = await asyncio.wait_for(ws.receive_json(), timeout=5.0)
        except Exception:  # noqa: BLE001 - timeout, bad JSON, disconnect
            await ws.close(code=4401)
            return
        if first.get("type") != "auth" or authenticate_key(st.settings, str(first.get("api_key", ""))) is None:
            st.audit.record("ws.auth_failed", "unknown", "denied")
            await ws.close(code=4401)
            return
    chans = {c.strip() for c in channels.split(",") if c.strip() in CHANNELS} or set(CHANNELS)
    await st.ws.connect(ws, chans)
    await ws.send_json(message("hello", {"channels": sorted(chans), "timezone": "UTC"}))
    try:
        while True:
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=20.0)
            except TimeoutError:
                await ws.send_json(message("ping", {}))
    except WebSocketDisconnect:
        return  # client left; connection cleanup happens in `finally`
    finally:
        st.ws.disconnect(ws)
