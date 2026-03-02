"""
Organisation-level rate limiting middleware.
"""

from __future__ import annotations

import asyncio
import math
import time
from collections import defaultdict, deque
from collections.abc import Callable

from redis.asyncio import Redis
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings
from app.core.security import TokenValidationError, verify_access_token

RATE_LIMIT_MAX_REQUESTS = 60
RATE_LIMIT_WINDOW_SECONDS = 60
_TARGET_PREFIXES = ("/api/analyse", "/api/summarise", "/api/jobs/")

_RATE_LIMIT_LOCK = asyncio.Lock()
_REQUEST_LOG: defaultdict[str, deque[float]] = defaultdict(deque)
_REDIS_CLIENT: Redis | None = None
_REDIS_LOCK = asyncio.Lock()


def reset_rate_limit_store() -> None:
    """Reset in-memory request log (used in tests)."""
    _REQUEST_LOG.clear()


async def _get_redis_client() -> Redis:
    global _REDIS_CLIENT
    if _REDIS_CLIENT is not None:
        return _REDIS_CLIENT

    async with _REDIS_LOCK:
        if _REDIS_CLIENT is None:
            settings = get_settings()
            _REDIS_CLIENT = Redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=0.2,
                socket_timeout=0.2,
            )
    return _REDIS_CLIENT


async def _check_and_record_memory(
    org_id: str,
    now_ts: float,
    max_requests: int,
    window_seconds: int,
) -> int | None:
    """
    Record request in local memory and return retry-after seconds if limited.
    """
    async with _RATE_LIMIT_LOCK:
        history = _REQUEST_LOG[org_id]
        threshold = now_ts - window_seconds
        while history and history[0] <= threshold:
            history.popleft()

        if len(history) >= max_requests:
            retry_after = max(1, math.ceil(window_seconds - (now_ts - history[0])))
            return retry_after

        history.append(now_ts)
        return None


async def _check_and_record_redis(
    org_id: str,
    now_ts: float,
    max_requests: int,
    window_seconds: int,
) -> int | None:
    """Record request in Redis and return retry-after seconds if limited."""
    window_start = int(now_ts // window_seconds) * window_seconds
    key = f"ratelimit:{org_id}:{window_start}"
    redis_client = await _get_redis_client()

    count = await redis_client.incr(key)
    if count == 1:
        await redis_client.expire(key, window_seconds)

    if count > max_requests:
        retry_after = max(1, window_seconds - (int(now_ts) - window_start))
        return retry_after
    return None


def _extract_org_id_from_auth_header(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    try:
        payload = verify_access_token(token)
    except TokenValidationError:
        return None
    org_id = payload.get("organisation_id")
    return str(org_id) if org_id else None


async def rate_limit_middleware_dispatch(request: Request, call_next: Callable) -> Response:
    """Apply per-organisation rolling-window rate limits for selected API routes."""
    path = request.url.path
    if not any(path.startswith(prefix) for prefix in _TARGET_PREFIXES):
        return await call_next(request)

    org_id = _extract_org_id_from_auth_header(request.headers.get("Authorization"))
    if not org_id:
        return await call_next(request)

    settings = get_settings()
    max_requests = max(1, RATE_LIMIT_MAX_REQUESTS)
    window_seconds = max(1, RATE_LIMIT_WINDOW_SECONDS)

    retry_after: int | None = None
    try:
        retry_after = await _check_and_record_redis(org_id, time.time(), max_requests, window_seconds)
    except Exception:
        # Fallback to in-memory limiter when Redis is unavailable.
        retry_after = await _check_and_record_memory(org_id, time.time(), max_requests, window_seconds)
        if retry_after is None and settings.rate_limit_fail_open:
            return await call_next(request)
        if retry_after is None and not settings.rate_limit_fail_open:
            return JSONResponse(
                status_code=503,
                content={"detail": "Rate limiter backend unavailable"},
            )

    if retry_after is not None:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
            headers={"Retry-After": str(retry_after)},
        )

    return await call_next(request)
