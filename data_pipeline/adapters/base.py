"""Data-source adapter interface and access-status model.

Adapters never scrape or bypass access controls. Restricted sources (IMDAA, NEPS-G, NCUM, IMD) read
*locally provisioned files* that a user with legitimate access has placed under ``DATA_PATH/<source>/``
and report ACCESS_REQUIRED / NOT_CONFIGURED until that is the case.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol

import xarray as xr

from ml.core.provenance import DataKind


class AccessStatus(StrEnum):
    AVAILABLE = "AVAILABLE"  # local files present and mapping configured
    DOWNLOADABLE = "DOWNLOADABLE"  # credentials configured; files can be fetched by the user's own account
    ACCESS_REQUIRED = "ACCESS_REQUIRED"  # no legitimate access/files yet
    NOT_CONFIGURED = "NOT_CONFIGURED"  # variable mapping missing


class AdapterError(RuntimeError):
    """Adapter failure with a user-actionable message (no secrets, no filesystem paths)."""


@dataclass(frozen=True)
class SourceDescriptor:
    """Public description of a source and whether it is usable right now."""

    name: str
    data_kind: DataKind
    status: AccessStatus
    message: str
    nominal_resolution_deg: float | None = None
    access_note: str = ""
    variables: tuple[str, ...] = ()


@dataclass(frozen=True)
class DatasetRequest:
    """What to load. ``bbox`` is (west, south, east, north); times are UTC."""

    variables: tuple[str, ...] = ()
    start: datetime | None = None
    end: datetime | None = None
    bbox: tuple[float, float, float, float] | None = None
    files: tuple[Path, ...] = field(default_factory=tuple)


class DataSourceAdapter(Protocol):
    """Interface every source implements."""

    name: str

    def descriptor(self) -> SourceDescriptor: ...
    def source_files(self, request: DatasetRequest) -> list[Path]: ...
    def open(self, request: DatasetRequest) -> xr.Dataset:
        """Return a lazily loaded dataset using *source-native* names and units (canonicalised later)."""
        ...
    def variable_map(self) -> dict[str, dict[str, str]]: ...
