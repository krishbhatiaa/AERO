"""Filesystem storage provider (development, tests, HPC POSIX storage)."""
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from data_pipeline.storage.base import StorageError, StoredObject
from data_pipeline.storage.keys import validate_key


class LocalStorageProvider:
    """Stores objects as files below ``root``. Every key is validated and re-checked against the root."""

    name = "local"

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        path = (self.root / validate_key(key)).resolve()
        if not path.is_relative_to(self.root):
            raise StorageError("key resolves outside the storage root")
        return path

    def put_bytes(self, key: str, data: bytes) -> StoredObject:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            os.replace(tmp, path)
        except OSError as exc:
            Path(tmp).unlink(missing_ok=True)
            raise StorageError("failed to write object") from exc
        return StoredObject(key, len(data), hashlib.sha256(data).hexdigest())

    def get_bytes(self, key: str) -> bytes:
        try:
            return self._resolve(key).read_bytes()
        except FileNotFoundError as exc:
            raise StorageError(f"object not found: {key}") from exc

    def exists(self, key: str) -> bool:
        return self._resolve(key).exists()

    def list_keys(self, prefix: str = "") -> list[str]:
        base = self.root
        keys = [p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file() and not p.name.startswith(".tmp-")]
        return sorted(k for k in keys if k.startswith(prefix))

    def delete(self, key: str) -> None:
        self._resolve(key).unlink(missing_ok=True)

    def healthcheck(self) -> tuple[bool, str]:
        try:
            probe = self.root / ".health"
            probe.write_text("ok")
            probe.unlink()
            return True, "writable"
        except OSError:
            return False, "storage root not writable"

    def zarr_target(self, key: str) -> tuple[str, dict[str, str] | None]:
        return str(self._resolve(key)), None

    def local_path(self, key: str) -> Path | None:
        return self._resolve(key)
