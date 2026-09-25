"""Factory for creating all repository instances bound to a PostgreSQL connection pool."""
from __future__ import annotations

import logging
from typing import Any

import asyncpg

from app.repositories.base import Repository
from app.repositories.postgres import (
    AlertRepository,
    AuditRepository,
    DatasetRepository,
    EventRepository,
    ForecastRepository,
    JobRepository,
    ModelRepository,
)

log = logging.getLogger("ewai.repositories.factory")


async def create_pool(database_url: str, min_size: int = 2, max_size: int = 10) -> asyncpg.Pool:
    return await asyncpg.create_pool(database_url, min_size=min_size, max_size=max_size)


async def create_repositories(database_url: str) -> dict[str, Repository]:
    pool = await create_pool(database_url)
    return {
        "events": EventRepository(pool),
        "forecasts": ForecastRepository(pool),
        "alerts": AlertRepository(pool),
        "datasets": DatasetRepository(pool),
        "jobs": JobRepository(pool),
        "models": ModelRepository(pool),
        "audit": AuditRepository(pool),
    }
