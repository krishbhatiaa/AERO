"""Create a storage provider from environment variables (never hard-code buckets or credentials)."""
from __future__ import annotations

import os
from collections.abc import Mapping

from data_pipeline.storage.base import StorageProvider
from data_pipeline.storage.local import LocalStorageProvider
from data_pipeline.storage.s3 import S3StorageProvider


def storage_from_env(env: Mapping[str, str] | None = None) -> StorageProvider:
    """``STORAGE_BACKEND=local|s3``; local uses ``DATA_PATH``; s3 uses S3_BUCKET/S3_ENDPOINT/S3_REGION/AWS_*."""
    e = env if env is not None else os.environ
    backend = e.get("STORAGE_BACKEND", "local").lower()
    if backend == "local":
        return LocalStorageProvider(e.get("DATA_PATH", "./var/data"))
    if backend == "s3":
        return S3StorageProvider(
            bucket=e.get("S3_BUCKET", ""), endpoint_url=e.get("S3_ENDPOINT") or None, region=e.get("S3_REGION") or None,
            access_key=e.get("AWS_ACCESS_KEY_ID") or None, secret_key=e.get("AWS_SECRET_ACCESS_KEY") or None,
        )
    raise ValueError(f"Unknown STORAGE_BACKEND {backend!r} (expected 'local' or 's3')")
