"""
Global structured error handling middleware.
"""

from __future__ import annotations

import json
import uuid
from http import HTTPStatus
from typing import Callable

from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


def _status_to_error(status_code: int) -> str:
    try:
        phrase = HTTPStatus(status_code).phrase
    except ValueError:
        return "http_error"
    return phrase.lower().replace(" ", "_")


def _extract_message(response: Response) -> str:
    try:
        payload = json.loads(response.body.decode("utf-8"))  # type: ignore[attr-defined]
        detail = payload.get("detail")
        if isinstance(detail, str):
            return detail
        if detail is not None:
            return "Validation error"
    except Exception:
        pass
    try:
        return HTTPStatus(response.status_code).phrase
    except ValueError:
        return "Request failed"


def _structured_error(
    request_id: str,
    status_code: int,
    message: str,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    merged_headers = dict(headers or {})
    merged_headers["X-Request-ID"] = request_id
    return JSONResponse(
        status_code=status_code,
        content={
            "error": _status_to_error(status_code),
            "message": message,
            "request_id": request_id,
        },
        headers=merged_headers,
    )


async def error_handling_middleware_dispatch(
    request: Request, call_next: Callable
) -> Response:
    """Ensure all error responses use structured format with request_id."""
    request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())
    request.state.request_id = request_id

    try:
        response = await call_next(request)
    except HTTPException as exc:
        return _structured_error(
            request_id=request_id,
            status_code=exc.status_code,
            message=str(exc.detail),
            headers=exc.headers or {},
        )
    except Exception:
        return _structured_error(
            request_id=request_id,
            status_code=500,
            message="Internal server error",
        )

    if response.status_code >= 400:
        return _structured_error(
            request_id=request_id,
            status_code=response.status_code,
            message=_extract_message(response),
            headers=dict(response.headers),
        )

    response.headers["X-Request-ID"] = request_id
    return response
