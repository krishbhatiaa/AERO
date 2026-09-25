"""Adapter registry and explicit source resolution (never silently substitute one dataset for another)."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from data_pipeline.adapters.base import AccessStatus, DataSourceAdapter, SourceDescriptor
from data_pipeline.adapters.sources import ADAPTERS

log = logging.getLogger(__name__)


def all_descriptors(data_root: Path | str | None = None) -> list[SourceDescriptor]:
    """Status of every configured source (used by ``/api/v1/data-sources`` and the dashboard)."""
    return [cls(data_root).descriptor() for cls in ADAPTERS.values()]


def _get_effective_mode() -> Literal["real", "demo"]:
    """Read mode from environment (avoids circular import with app.core.config)."""
    real_data = os.environ.get("REAL_DATA_MODE", "").lower() in ("true", "1", "yes")
    if real_data:
        return "real"
    return "demo"


@dataclass(frozen=True)
class SourceResolution:
    """Outcome of asking for a source: what was requested, what will be used, and why."""

    requested: str
    used: str
    substituted: bool
    message: str
    mode: Literal["real", "demo"] = field(default_factory=_get_effective_mode)


def resolve_source(requested: str, fallback: str = "era5", data_root: Path | str | None = None) -> SourceResolution:
    """Return the requested source if usable, otherwise an *explicitly reported* fallback."""
    key = requested.lower()
    mode = _get_effective_mode()

    if key not in ADAPTERS:
        raise ValueError(f"Unknown source {requested!r}; known: {sorted(ADAPTERS)}")

    adapter: DataSourceAdapter = ADAPTERS[key](data_root)
    d = adapter.descriptor()

    if d.status in (AccessStatus.AVAILABLE, AccessStatus.DOWNLOADABLE):
        return SourceResolution(d.name, d.name, False, d.message, mode)

    if mode == "real":
        raise RuntimeError(
            f"REAL_DATA_MODE is active but source {requested!r} is not available. "
            f"Status: {d.status.value}. Message: {d.message}. "
            "Download data first: python scripts/download_era5.py --help"
        )

    fb = ADAPTERS[fallback](data_root).descriptor()
    used = fb.name if fb.status in (AccessStatus.AVAILABLE, AccessStatus.DOWNLOADABLE) else None
    if used is None:
        raise RuntimeError(
            f"Source {requested!r} is not available (status: {d.status.value}) "
            f"and fallback source {fallback!r} is also not available. "
            "Download data first: python scripts/download_era5.py --help"
        )
    msg = f"{d.name} source configured. Status: {d.status.value.replace('_', ' ')}. Using {used} development dataset."
    log.warning(
        "Source fallback occurred",
        extra={"requested": requested, "used": used, "mode": mode, "reason": msg},
    )
    return SourceResolution(d.name, used, True, msg, mode)
