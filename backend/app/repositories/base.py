"""Abstract repository protocol for data access."""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Repository(Protocol):
    async def get(self, id: str) -> dict | None: ...

    async def create(self, data: dict) -> str: ...

    async def update(self, id: str, data: dict) -> bool: ...

    async def delete(self, id: str) -> bool: ...

    async def list(self, limit: int = 100, offset: int = 0) -> list[dict]: ...
