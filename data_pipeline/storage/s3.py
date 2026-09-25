"""S3-compatible storage provider (MinIO in development, AWS S3 / compatible in production).

Configuration is injected by the caller (from environment variables); nothing is hard-coded.
``boto3`` is imported lazily so the package works without it installed.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from data_pipeline.storage.base import StorageError, StoredObject
from data_pipeline.storage.keys import validate_key


class S3StorageProvider:
    """Object storage via the S3 API."""

    name = "s3"

    def __init__(
        self, bucket: str, endpoint_url: str | None = None, region: str | None = None,
        access_key: str | None = None, secret_key: str | None = None, create_bucket: bool = False,
        client: object | None = None,
    ) -> None:
        if not bucket:
            raise ValueError("bucket is required (set S3_BUCKET)")
        self.bucket = bucket
        self.endpoint_url = endpoint_url
        self._access_key, self._secret_key = access_key, secret_key
        if client is None:
            try:
                import boto3
            except ImportError as exc:  # pragma: no cover - exercised only without boto3
                raise StorageError("boto3 is not installed; install the 's3' extra") from exc
            client = boto3.client(
                "s3", endpoint_url=endpoint_url, region_name=region,
                aws_access_key_id=access_key, aws_secret_access_key=secret_key,
            )
        self._c = client
        if create_bucket:
            try:
                self._c.head_bucket(Bucket=bucket)
            except Exception:  # noqa: BLE001 - boto raises ClientError subclasses; any failure means "create"
                self._c.create_bucket(Bucket=bucket)

    def put_bytes(self, key: str, data: bytes) -> StoredObject:
        key = validate_key(key)  # invalid keys raise InvalidKeyError (same contract as the local provider)
        try:
            self._c.put_object(Bucket=self.bucket, Key=key, Body=data)
        except Exception as exc:  # noqa: BLE001
            raise StorageError("failed to write object") from exc
        return StoredObject(key, len(data), hashlib.sha256(data).hexdigest())

    def get_bytes(self, key: str) -> bytes:
        key = validate_key(key)
        try:
            return self._c.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except Exception as exc:  # noqa: BLE001
            raise StorageError(f"object not found or unreadable: {key}") from exc

    def exists(self, key: str) -> bool:
        key = validate_key(key)
        try:
            self._c.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:  # noqa: BLE001
            return False

    def list_keys(self, prefix: str = "") -> list[str]:
        keys: list[str] = []
        pager = self._c.get_paginator("list_objects_v2")
        for page in pager.paginate(Bucket=self.bucket, Prefix=prefix):
            keys.extend(o["Key"] for o in page.get("Contents", []))
        return sorted(keys)

    def delete(self, key: str) -> None:
        self._c.delete_object(Bucket=self.bucket, Key=validate_key(key))

    def healthcheck(self) -> tuple[bool, str]:
        try:
            self._c.head_bucket(Bucket=self.bucket)
            return True, "bucket reachable"
        except Exception:  # noqa: BLE001
            return False, "bucket unreachable"

    def zarr_target(self, key: str) -> tuple[str, dict[str, str] | None]:
        opts: dict[str, str] = {}
        if self.endpoint_url:
            opts["endpoint_url"] = self.endpoint_url
        if self._access_key and self._secret_key:
            opts.update({"key": self._access_key, "secret": self._secret_key})
        return f"s3://{self.bucket}/{validate_key(key)}", opts or None

    def local_path(self, key: str) -> Path | None:
        return None
