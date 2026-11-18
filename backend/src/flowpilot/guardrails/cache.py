"""Redis-backed Tier 0 response cache with graceful in-memory fallback."""

from __future__ import annotations

import contextlib
import hashlib
import json
import time
from typing import Any

from redis.asyncio import Redis

from flowpilot.config import get_settings
from flowpilot.observability.metrics import CACHE_HITS_TOTAL


class Tier0Cache:
    """Deterministic cache keyed by normalized query + sorted document content hashes."""

    def __init__(self, *, ttl_seconds: int = 900) -> None:
        self.ttl_seconds = ttl_seconds
        self._memory: dict[str, tuple[float, dict[str, Any]]] = {}
        self._redis: Redis | None = None
        self._redis_unavailable: bool = False

    async def _get_redis(self) -> Redis | None:
        if self._redis_unavailable:
            return None
        if self._redis is None:
            settings = get_settings()
            if settings.env == "test":
                self._redis_unavailable = True
                return None
            try:
                client = Redis.from_url(
                    settings.redis_url, decode_responses=True, socket_connect_timeout=0.5
                )
                await client.ping()
                self._redis = client
            except Exception:
                self._redis_unavailable = True
                return None
        return self._redis

    @staticmethod
    def build_key(*, query: str, doc_hashes: list[str], extra: str = "") -> str:
        normalized_q = " ".join(query.lower().strip().split())
        payload = f"{normalized_q}|{'|'.join(sorted(doc_hashes))}|{extra}"
        return "fp:cache:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()

    async def get(self, key: str) -> dict[str, Any] | None:
        redis_client = await self._get_redis()
        if redis_client is not None:
            with contextlib.suppress(Exception):
                raw = await redis_client.get(key)
                if raw:
                    CACHE_HITS_TOTAL.labels(cache_type="redis").inc()
                    return json.loads(raw)

        entry = self._memory.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() > expires_at:
            self._memory.pop(key, None)
            return None
        CACHE_HITS_TOTAL.labels(cache_type="memory").inc()
        return value

    async def set(self, key: str, value: dict[str, Any]) -> None:
        self._memory[key] = (time.monotonic() + self.ttl_seconds, value)
        redis_client = await self._get_redis()
        if redis_client is not None:
            with contextlib.suppress(Exception):
                await redis_client.set(key, json.dumps(value), ex=self.ttl_seconds)

    def clear(self) -> None:
        self._memory.clear()


_cache = Tier0Cache()


def get_tier0_cache() -> Tier0Cache:
    return _cache
