"""Revoked-token store for logout.

Uses Redis when REDIS_URL is set (Docker), otherwise an in-memory dict.
In-memory is fine for the standalone install (one server process); its only
cost is that revocations are forgotten on restart, and access tokens expire
on their own within ACCESS_TOKEN_EXPIRE_MINUTES anyway.
"""

import logging
import time
from functools import lru_cache
from typing import Protocol

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_KEY = "token:blacklist:{}"


class TokenStore(Protocol):
    async def revoke(self, token: str, ttl_seconds: int) -> None: ...
    async def is_revoked(self, token: str) -> bool: ...


class MemoryTokenStore:
    def __init__(self) -> None:
        self._expiry: dict[str, float] = {}

    async def revoke(self, token: str, ttl_seconds: int) -> None:
        now = time.time()
        # Drop expired entries so the dict can't grow forever
        self._expiry = {t: exp for t, exp in self._expiry.items() if exp > now}
        self._expiry[token] = now + max(ttl_seconds, 1)

    async def is_revoked(self, token: str) -> bool:
        exp = self._expiry.get(token)
        return exp is not None and exp > time.time()


class RedisTokenStore:
    def __init__(self, url: str) -> None:
        import redis.asyncio as redis

        self._redis = redis.from_url(url)

    async def revoke(self, token: str, ttl_seconds: int) -> None:
        await self._redis.set(_KEY.format(token), "1", ex=max(ttl_seconds, 1))

    async def is_revoked(self, token: str) -> bool:
        return bool(await self._redis.get(_KEY.format(token)))


@lru_cache
def get_token_store() -> TokenStore:
    url = get_settings().redis_url
    if url:
        logger.info("Token store: Redis")
        return RedisTokenStore(url)
    logger.info("Token store: in-memory (REDIS_URL not set)")
    return MemoryTokenStore()
