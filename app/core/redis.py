"""
Shared async Redis client helper.
"""

from __future__ import annotations

import asyncio

from redis.asyncio import Redis

from app.core.config import get_settings

_REDIS_CLIENT: Redis | None = None
_REDIS_LOCK = asyncio.Lock()


async def get_redis_client() -> Redis:
    """Return cached Redis client instance."""
    global _REDIS_CLIENT
    if _REDIS_CLIENT is not None:
        return _REDIS_CLIENT

    async with _REDIS_LOCK:
        if _REDIS_CLIENT is None:
            settings = get_settings()
            url = settings.redis_url
            kwargs = {
                "decode_responses": True,
                "socket_connect_timeout": 1.0,
                "socket_timeout": 1.0,
            }
            if url.startswith("rediss://"):
                kwargs["ssl_cert_reqs"] = None
            _REDIS_CLIENT = Redis.from_url(
                url,
                **kwargs,
            )
    return _REDIS_CLIENT
