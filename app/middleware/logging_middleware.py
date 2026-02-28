"""
Request logging middleware.
Generates request_id, measures duration, logs request lifecycle.
"""

import time
import uuid
from typing import Callable

from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import (
    bind_request_context,
    clear_request_context,
    get_logger,
)

logger = get_logger(__name__)


async def logging_middleware_dispatch(
    request: Request, call_next: Callable
) -> Response:
    """
    Standalone dispatch for use with app.middleware("http").
    Wraps request with request_id, timing, and structured logging.
    """
    request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())
    request.state.request_id = request_id
    method = request.method
    path = request.url.path

    organisation_id = getattr(request.state, "org_id", None)
    user_id = getattr(request.state, "user_id", None)

    bind_request_context(
        request_id=request_id,
        method=method,
        path=path,
        organisation_id=str(organisation_id) if organisation_id else None,
        user_id=str(user_id) if user_id else None,
    )

    logger.info(
        "request_started",
        request_id=request_id,
        method=method,
        path=path,
    )

    start = time.perf_counter()
    response_status = 500

    try:
        response = await call_next(request)
        response_status = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    except Exception as exc:
        logger.exception(
            "request_failed",
            error=str(exc),
            request_id=request_id,
            method=method,
            path=path,
        )
        raise
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "request_completed",
            request_id=request_id,
            method=method,
            path=path,
            response_status=response_status,
            duration_ms=round(duration_ms, 2),
            organisation_id=str(organisation_id) if organisation_id else None,
            user_id=str(user_id) if user_id else None,
        )
        clear_request_context()
