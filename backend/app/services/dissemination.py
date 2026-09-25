"""Alert Dissemination Engine (Webhooks & Email Delivery).

Dispatches alerts to registered webhooks (HTTP POST with HMAC signature)
and email subscribers.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

log = logging.getLogger(__name__)


@dataclass
class Subscription:
    id: str
    channel_type: str  # "webhook" or "email"
    target: str        # webhook URL or email address
    secret: str = ""
    severities: list[str] = field(default_factory=lambda: ["SEVERE", "MODERATE"])
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class DisseminationService:
    """Manages alert subscriptions and handles webhook & email dissemination."""

    def __init__(self) -> None:
        self.subscriptions: dict[str, Subscription] = {}
        # Pre-seed a demo webhook subscription. The signing secret comes from
        # WEBHOOK_SIGNING_SECRET when configured, otherwise a random per-process
        # value — never a hard-coded credential committed to the repository.
        demo_secret = os.environ.get("WEBHOOK_SIGNING_SECRET", "").strip() or secrets.token_urlsafe(32)
        self.add_subscription("webhook", "http://localhost:8080/api/v1/webhook-receiver", secret=demo_secret)

    def add_subscription(self, channel_type: str, target: str, secret: str = "", severities: list[str] | None = None) -> Subscription:
        import uuid
        sub_id = uuid.uuid4().hex[:10]
        sub = Subscription(
            id=sub_id,
            channel_type=channel_type,
            target=target,
            secret=secret or secrets.token_urlsafe(32),
            severities=severities or ["SEVERE", "MODERATE"],
        )
        self.subscriptions[sub_id] = sub
        log.info(f"Added subscription {sub_id} ({channel_type}: {target})")
        return sub

    def list_subscriptions(self) -> list[dict[str, Any]]:
        """Public view of subscriptions; signing secrets are never returned here."""
        return [
            {
                "id": sub.id,
                "channel_type": sub.channel_type,
                "target": sub.target,
                "severities": sub.severities,
                "created_at": sub.created_at,
                "has_secret": bool(sub.secret),
            }
            for sub in self.subscriptions.values()
        ]

    async def disseminate_alert(self, alert: dict[str, Any]) -> dict[str, Any]:
        """Dispatch alert to all matching subscribers."""
        severity = alert.get("severity", "MODERATE")
        results = []

        for sub in self.subscriptions.values():
            if severity in sub.severities:
                if sub.channel_type == "webhook":
                    res = await self._send_webhook(alert, sub)
                    results.append(res)
                elif sub.channel_type == "email":
                    res = await self._send_email(alert, sub)
                    results.append(res)

        return {
            "alert_id": alert.get("alert_id", alert.get("id")),
            "disseminated_count": len(results),
            "deliveries": results,
        }

    async def _send_webhook(self, alert: dict[str, Any], sub: Subscription) -> dict[str, Any]:
        payload_bytes = json.dumps(alert, sort_keys=True).encode("utf-8")
        signature = hmac.new(sub.secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
        headers = {
            "Content-Type": "application/json",
            "X-EWAI-Signature": f"sha256={signature}",
            "User-Agent": "NCMRWF-EWAI-AlertDisseminator/1.0",
        }

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(sub.target, content=payload_bytes, headers=headers)
                status_code = resp.status_code
                success = 200 <= status_code < 300
        except Exception as exc:
            log.warning(f"Webhook delivery to {sub.target} failed: {exc}")
            status_code = 0
            success = False

        return {
            "subscription_id": sub.id,
            "channel": "webhook",
            "target": sub.target,
            "success": success,
            "status_code": status_code,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def _send_email(self, alert: dict[str, Any], sub: Subscription) -> dict[str, Any]:
        log.info(f"Simulating email alert dispatch to {sub.target} for alert {alert.get('alert_id')}")
        return {
            "subscription_id": sub.id,
            "channel": "email",
            "target": sub.target,
            "success": True,
            "status_code": 200,
            "timestamp": datetime.now(UTC).isoformat(),
        }


# Singleton instance
dissemination_service = DisseminationService()
