"""Data-kind labels and provenance records.

Every array, event, alert and map layer carries a :class:`DataKind`. Products derived from several
inputs inherit the *weakest* label via :func:`combine_kinds`, so synthetic data can never be
presented as observed, and model output can never be presented as reanalysis.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class DataKind(StrEnum):
    """What a dataset or product fundamentally is."""

    OBSERVED = "OBSERVED"
    REANALYSIS = "REANALYSIS"
    FORECAST = "FORECAST"
    MODEL_PREDICTION = "MODEL_PREDICTION"
    SYNTHETIC_DEMO = "SYNTHETIC_DEMO"


# Weakest (least trustworthy as a statement about the real atmosphere) first.
_WEAKEST_FIRST: tuple[DataKind, ...] = (
    DataKind.SYNTHETIC_DEMO,
    DataKind.MODEL_PREDICTION,
    DataKind.FORECAST,
    DataKind.REANALYSIS,
    DataKind.OBSERVED,
)


def combine_kinds(*kinds: DataKind) -> DataKind:
    """Return the weakest label among ``kinds`` (the label a derived product must carry)."""
    if not kinds:
        raise ValueError("combine_kinds requires at least one DataKind")
    present = set(kinds)
    for kind in _WEAKEST_FIRST:
        if kind in present:
            return kind
    raise ValueError(f"Unknown data kind(s): {kinds!r}")  # pragma: no cover


def config_hash(config: Any) -> str:
    """Stable 16-hex-char SHA-256 digest of a JSON-serialisable configuration."""
    payload = json.dumps(config, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class Provenance(BaseModel):
    """Traceability record attached to every derived product."""

    data_source: str
    data_kind: DataKind
    dataset_id: str | None = None
    dataset_version: str | None = None
    initialization_time: datetime | None = None
    valid_time: datetime | None = None
    model_version: str | None = None
    checkpoint_sha256: str | None = None
    preprocess_config_hash: str | None = None
    pipeline_config_hash: str | None = None
    git_sha: str | None = None
    notes: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
