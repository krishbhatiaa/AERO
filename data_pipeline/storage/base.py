"""Storage abstraction. Bucket names, endpoints and credentials always come from the environment."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class StoredObject:
    """Result of a write."""

    key: str
    size: int
    sha256: str


class StorageError(RuntimeError):
    """Storage backend failure (message never contains credentials or filesystem paths)."""


class StorageProvider(Protocol):
    """Interface implemented by :class:`LocalStorageProvider` and :class:`S3StorageProvider`."""

    name: str

    def put_bytes(self, key: str, data: bytes) -> StoredObject: ...
    def get_bytes(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def list_keys(self, prefix: str = "") -> list[str]: ...
    def delete(self, key: str) -> None: ...
    def healthcheck(self) -> tuple[bool, str]: ...
    def zarr_target(self, key: str) -> tuple[str, dict[str, str] | None]:
        """``(url_or_path, storage_options)`` suitable for ``Dataset.to_zarr`` / ``xr.open_zarr``."""
        ...

    def local_path(self, key: str) -> Path | None: ...
