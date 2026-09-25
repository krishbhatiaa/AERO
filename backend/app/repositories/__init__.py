"""Repository layer for the extreme-weather-ai backend."""
from __future__ import annotations

from app.repositories.base import Repository

__all__ = ["Repository"]


def __getattr__(name: str):
    if name == "create_repositories":
        from app.repositories.factory import create_repositories
        return create_repositories
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
