"""Object-store key validation and construction (path-traversal safe)."""
from __future__ import annotations

import re

_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._=\-]*(/[A-Za-z0-9][A-Za-z0-9._=\-]*)*/?$")
MAX_KEY_LENGTH = 512


class InvalidKeyError(ValueError):
    """Raised for keys that are empty, absolute, contain traversal segments or unsafe characters."""


def validate_key(key: str) -> str:
    """Return ``key`` if it is a safe relative key, else raise :class:`InvalidKeyError`."""
    if not key or len(key) > MAX_KEY_LENGTH:
        raise InvalidKeyError("key must be 1..512 characters")
    if ".." in key.split("/") or "//" in key or key.startswith("/") or "\\" in key or "\x00" in key:
        raise InvalidKeyError("key contains a traversal or absolute segment")
    if not _KEY_RE.match(key):
        raise InvalidKeyError("key contains unsupported characters")
    return key


def build_key(*parts: str) -> str:
    """Join validated segments into a key, e.g. ``build_key('staged', 'era5', 'x.zarr')``."""
    return validate_key("/".join(p.strip("/") for p in parts))
