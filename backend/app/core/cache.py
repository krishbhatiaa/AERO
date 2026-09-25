"""Response/result cache. Redis when reachable, otherwise an in-process TTL cache (with a logged fallback)."""
from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from threading import Lock
from typing import Any, Protocol

log = logging.getLogger("app.cache")


class CacheBackend(Protocol):
    name: str

    def get(self, key: str) -> Any | None: ...
    def set(self, key: str, value: Any, ttl_s: int) -> None: ...
    def get_or_set(self, key: str, ttl_s: int, factory: Callable[[], Any]) -> Any: ...


class MemoryCache:
    """Bounded in-process TTL cache."""

    name = "memory"

    def __init__(self, max_items: int = 512) -> None:
        self._d: dict[str, tuple[float, Any]] = {}
        self._max, self._lock = max_items, Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            item = self._d.get(key)
            if item is None or item[0] < time.monotonic():
                self._d.pop(key, None)
                return None
            return item[1]

    def set(self, key: str, value: Any, ttl_s: int) -> None:
        with self._lock:
            if len(self._d) >= self._max:
                self._d.pop(min(self._d, key=lambda k: self._d[k][0]))
            self._d[key] = (time.monotonic() + ttl_s, value)

    def get_or_set(self, key: str, ttl_s: int, factory: Callable[[], Any]) -> Any:
        hit = self.get(key)
        if hit is not None:
            return hit
        value = factory()
        self.set(key, value, ttl_s)
        return value


class RedisCache:
    """JSON-serialised Redis cache. Any Redis error degrades to computing the value (never fails a request)."""

    name = "redis"

    def __init__(self, client: Any, prefix: str = "ewai:") -> None:
        self._r, self._p = client, prefix

    def get(self, key: str) -> Any | None:
        try:
            raw = self._r.get(self._p + key)
            return json.loads(raw) if raw is not None else None
        except Exception:  # noqa: BLE001
            log.warning("redis get failed; treating as cache miss")
            return None

    def set(self, key: str, value: Any, ttl_s: int) -> None:
        try:
            self._r.set(self._p + key, json.dumps(value), ex=ttl_s)
        except Exception:  # noqa: BLE001
            log.warning("redis set failed; value not cached")

    def get_or_set(self, key: str, ttl_s: int, factory: Callable[[], Any]) -> Any:
        hit = self.get(key)
        if hit is not None:
            return hit
        value = factory()
        self.set(key, value, ttl_s)
        return value


def create_cache(redis_url: str) -> CacheBackend:
    """Use Redis if ``redis_url`` is set and answers PING; otherwise fall back (logged) to the memory cache."""
    if redis_url:
        try:
            import redis

            client = redis.Redis.from_url(redis_url, socket_connect_timeout=1, socket_timeout=1)
            client.ping()
            return RedisCache(client)
        except Exception:  # noqa: BLE001
            log.warning("Redis unavailable; falling back to in-memory cache")
    return MemoryCache()
