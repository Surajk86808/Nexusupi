"""
Organisation-level rate limiting middleware.
"""

from __future__ import annotations

import asyncio
import math
import time
from collections import defaultdict, deque
from collections.abc import Callable

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.security import TokenValidationError, verify_access_token

RATE_LIMIT_MAX_REQUESTS = 60
RATE_LIMIT_WINDOW_SECONDS = 60
_TARGET_PREFIXES = ("/api/analyse", "/api/summarise", "/api/jobs/")

_RATE_LIMIT_LOCK = asyncio.Lock()
_REQUEST_LOG: defaultdict[str, deque[float]] = defaultdict(deque)


def reset_rate_limit_store() -> None:
    """Reset in-memory request log (used in tests)."""
    _REQUEST_LOG.clear()


async def _check_and_record(org_id: str, now_ts: float) -> int | None:
    """
    Record request for organisation and return retry-after seconds if limited.
    """
    async with _RATE_LIMIT_LOCK:
        history = _REQUEST_LOG[org_id]
        threshold = now_ts - RATE_LIMIT_WINDOW_SECONDS
        while history and history[0] <= threshold:
            history.popleft()

        if len(history) >= RATE_LIMIT_MAX_REQUESTS:
            retry_after = max(1, math.ceil(RATE_LIMIT_WINDOW_SECONDS - (now_ts - history[0])))
            return retry_after

        history.append(now_ts)
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

    retry_after = await _check_and_record(org_id, time.time())
    if retry_after is not None:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
            headers={"Retry-After": str(retry_after)},
        )

    return await call_next(request)
