"""
Global structured error handling middleware.
"""

from __future__ import annotations

import json
import uuid
from http import HTTPStatus
from typing import Any, Callable

from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


def _status_to_error(status_code: int) -> str:
    try:
        phrase = HTTPStatus(status_code).phrase
    except ValueError:
        return "http_error"
    return phrase.lower().replace(" ", "_")


def _extract_message(status_code: int, detail: Any) -> str:
    if isinstance(detail, str):
        return detail
    if isinstance(detail, dict) and isinstance(detail.get("message"), str):
        return detail["message"]
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return "Request failed"


def _structured_error(
    request_id: str,
    status_code: int,
    message: str,
    detail: Any = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    source_headers = dict(headers or {})
    merged_headers: dict[str, str] = {}
    # Only forward protocol-relevant headers that should survive
    # response body rewrites.
    for key in ("WWW-Authenticate", "Retry-After"):
        if key in source_headers:
            merged_headers[key] = source_headers[key]
        elif key.lower() in source_headers:
            merged_headers[key] = source_headers[key.lower()]
    merged_headers["X-Request-ID"] = request_id
    content: dict[str, Any] = {
        "error": _status_to_error(status_code),
        "message": message,
        "request_id": request_id,
    }
    if isinstance(detail, dict):
        if isinstance(detail.get("error"), str):
            content["error"] = detail["error"]
        if isinstance(detail.get("message"), str):
            content["message"] = detail["message"]
        for key, value in detail.items():
            if key not in {"request_id"}:
                content[key] = value
    return JSONResponse(status_code=status_code, content=content, headers=merged_headers)


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
        detail: Any = None
        try:
            body = getattr(response, "body", None)
            if body is None and hasattr(response, "body_iterator"):
                chunks: list[bytes] = []
                async for chunk in response.body_iterator:  # type: ignore[attr-defined]
                    chunks.append(chunk if isinstance(chunk, bytes) else str(chunk).encode("utf-8"))
                body = b"".join(chunks)
            if body:
                payload = json.loads(body.decode("utf-8"))
                detail = payload.get("detail")
        except Exception:
            detail = None
        return _structured_error(
            request_id=request_id,
            status_code=response.status_code,
            message=_extract_message(response.status_code, detail),
            detail=detail,
            headers=dict(response.headers),
        )

    response.headers["X-Request-ID"] = request_id
    return response
