"""Product store: in-memory (demo) and PostgreSQL-backed implementations.

Repository boundary: the API only talks to :class:`ProductStore` or
:class:`PostgresProductStore`.  The schema is in ``database/schema/001_init.sql``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.services import alerts as alert_service
from app.services import events as ev

from ml.pipeline.demo import DemoResult
from ml.tracking.tracker import Track

log = logging.getLogger("app.store")


@dataclass
class EventRecord:
    id: str
    track: Track
    summary: dict[str, Any]


class ProductStore:
    """Holds the latest :class:`DemoResult` plus the derived events and alerts."""

    def __init__(self, result: DemoResult) -> None:
        self.result = result
        self.built_at = datetime.now(UTC)
        self.events: dict[str, EventRecord] = {}
        self.alerts: dict[str, dict[str, Any]] = {}
        tracks = getattr(result, "tracks", None) or ([result.primary] if hasattr(result, "primary") and result.primary else [])
        # Filter to significant tracks only (peak intensity >= 1.0 mm/6h) and cap at top 15
        def _peak_intensity(t: Any) -> float:
            obs = getattr(t, "observed_points", [])
            return max((p.max_intensity or 0.0 for p in obs), default=0.0)
        sig_tracks = [t for t in tracks if _peak_intensity(t) >= 1.0]
        if not sig_tracks:
            sig_tracks = tracks  # fallback: keep all if none pass filter
        # Keep top 15 by peak intensity
        sig_tracks = sorted(sig_tracks, key=_peak_intensity, reverse=True)[:15]
        for track in sig_tracks:
            try:
                summary = ev.event_summary(result, track)
                self.events[summary["id"]] = EventRecord(summary["id"], track, summary)
                alert = alert_service.build_alert(result, track)
                self.alerts[alert["id"]] = alert
            except Exception:
                continue
        if not self.events and hasattr(result, "primary") and result.primary:
            track = result.primary
            summary = ev.event_summary(result, track)
            self.events[summary["id"]] = EventRecord(summary["id"], track, summary)
            alert = alert_service.build_alert(result, track)
            self.alerts[alert["id"]] = alert
        self.forecast = ev.forecast_run(result)

    def event(self, event_id: str) -> EventRecord | None:
        return self.events.get(event_id)


class PostgresProductStore:
    """PostgreSQL-backed store that delegates to repository objects.

    Falls back gracefully to in-memory dicts when the database is unavailable.
    """

    def __init__(self, repositories: dict[str, Any] | None = None) -> None:
        self._repos = repositories or {}
        self.events: dict[str, EventRecord] = {}
        self.alerts: dict[str, dict[str, Any]] = {}
        self.forecast: dict[str, Any] = {}
        self.built_at = datetime.now(UTC)
        self.result: DemoResult | None = None

    async def load_events(self) -> list[dict[str, Any]]:
        repo = self._repos.get("events")
        if repo is None:
            return list(self.events.values()) if self.events else []
        try:
            rows = await repo.list(limit=500)
            return rows
        except Exception:  # noqa: BLE001
            log.warning("failed to load events from database", exc_info=True)
            return list(self.events.values()) if self.events else []

    async def load_forecasts(self) -> list[dict[str, Any]]:
        repo = self._repos.get("forecasts")
        if repo is None:
            return [self.forecast] if self.forecast else []
        try:
            return await repo.list(limit=100)
        except Exception:  # noqa: BLE001
            log.warning("failed to load forecasts from database", exc_info=True)
            return [self.forecast] if self.forecast else []

    async def load_alerts(self) -> list[dict[str, Any]]:
        repo = self._repos.get("alerts")
        if repo is None:
            return list(self.alerts.values()) if self.alerts else []
        try:
            return await repo.list(limit=500)
        except Exception:  # noqa: BLE001
            log.warning("failed to load alerts from database", exc_info=True)
            return list(self.alerts.values()) if self.alerts else []

    async def persist_event(self, event_data: dict[str, Any]) -> str | None:
        repo = self._repos.get("events")
        if repo is None:
            return None
        try:
            return await repo.create(event_data)
        except Exception:  # noqa: BLE001
            log.warning("failed to persist event", exc_info=True)
            return None

    async def persist_alert(self, alert_data: dict[str, Any]) -> str | None:
        repo = self._repos.get("alerts")
        if repo is None:
            return None
        try:
            return await repo.create(alert_data)
        except Exception:  # noqa: BLE001
            log.warning("failed to persist alert", exc_info=True)
            return None

    async def persist_forecast(self, forecast_data: dict[str, Any]) -> str | None:
        repo = self._repos.get("forecasts")
        if repo is None:
            return None
        try:
            return await repo.create(forecast_data)
        except Exception:  # noqa: BLE001
            log.warning("failed to persist forecast", exc_info=True)
            return None

    def event(self, event_id: str) -> EventRecord | None:
        return self.events.get(event_id)

    def populate_from_result(self, result: DemoResult) -> None:
        self.result = result
        self.built_at = datetime.now(UTC)
        tracks = getattr(result, "tracks", None) or ([result.primary] if result.primary else [])
        events = {}
        alerts = {}
        for track in tracks:
            try:
                summary = ev.event_summary(result, track)
                events[summary["id"]] = EventRecord(summary["id"], track, summary)
                alert = alert_service.build_alert(result, track)
                alerts[alert["id"]] = alert
            except Exception:
                log.warning("failed to build event/alert for track", exc_info=True)
        if not events and result.primary:
            summary = ev.event_summary(result, result.primary)
            events[summary["id"]] = EventRecord(summary["id"], result.primary, summary)
            alert = alert_service.build_alert(result, result.primary)
            alerts[alert["id"]] = alert
        self.events = events
        self.alerts = alerts
        self.forecast = ev.forecast_run(result)
