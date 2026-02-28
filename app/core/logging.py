"""
Production-grade structured logging using structlog.
Supports JSON output (production) and console output (development).
"""

import logging
import sys
from typing import Any

import structlog

from app.core.config import get_settings


def _get_renderer():
    """Return JSON or Console renderer based on environment."""
    settings = get_settings()
    if settings.environment == "production":
        return structlog.processors.JSONRenderer()
    return structlog.dev.ConsoleRenderer(colors=True)


class _SafePrintLogger:
    """Logger that tolerates closed stdout (e.g. under pytest capture)."""

    def _write(self, message: str) -> None:
        try:
            print(message, file=sys.stdout, flush=True)
        except (ValueError, OSError):
            pass

    def msg(self, message: str, **kwargs: Any) -> None:
        self._write(message)

    def info(self, message: str, **kwargs: Any) -> None:
        self._write(message)

    def debug(self, message: str, **kwargs: Any) -> None:
        self._write(message)

    def warning(self, message: str, **kwargs: Any) -> None:
        self._write(message)

    def error(self, message: str, **kwargs: Any) -> None:
        self._write(message)

    def critical(self, message: str, **kwargs: Any) -> None:
        self._write(message)

    def exception(self, message: str, **kwargs: Any) -> None:
        self._write(message)


def _safe_logger_factory(*args: Any, **kwargs: Any) -> _SafePrintLogger:
    return _SafePrintLogger()


def configure_logging() -> None:
    """
    Configure structlog. Call once at application startup.
    Uses LOG_LEVEL and ENVIRONMENT from settings.
    """
    settings = get_settings()
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    structlog.configure(
        cache_logger_on_first_use=True,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _get_renderer(),
        ],
        logger_factory=_safe_logger_factory,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Return a bound logger with the given name.
    Use for module-level loggers: get_logger(__name__).
    """
    return structlog.get_logger(name)


def bind_request_context(
    request_id: str,
    method: str | None = None,
    path: str | None = None,
    organisation_id: str | None = None,
    user_id: str | None = None,
) -> None:
    """Bind request context for structured logging. Call from middleware."""
    context: dict[str, Any] = {"request_id": request_id}
    if method is not None:
        context["method"] = method
    if path is not None:
        context["path"] = path
    if organisation_id is not None:
        context["organisation_id"] = organisation_id
    if user_id is not None:
        context["user_id"] = user_id
    structlog.contextvars.bind_contextvars(**context)


def clear_request_context() -> None:
    """Clear request context. Call at end of request."""
    structlog.contextvars.clear_contextvars()
