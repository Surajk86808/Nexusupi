"""
ARQ worker configuration and job handlers.
"""

from __future__ import annotations

from typing import Any

from arq.connections import RedisSettings

from app.api.routes.product import _JOB_LOCK, _JOB_STORE
from app.core.config import get_settings

settings = get_settings()


async def summarise_job(ctx: dict[str, Any], job_id: str, organisation_id: str, text: str) -> None:
    """Process summarisation jobs and persist status/result to in-memory job store."""
    try:
        word_count = len(text.split())
        summary = f"Summary: {word_count} words processed."
        async with _JOB_LOCK:
            existing = _JOB_STORE.get(job_id, {})
            existing.update(
                {
                    "job_id": job_id,
                    "organisation_id": organisation_id,
                    "status": "completed",
                    "result": summary,
                    "error": None,
                }
            )
            _JOB_STORE[job_id] = existing
    except Exception as exc:
        async with _JOB_LOCK:
            existing = _JOB_STORE.get(job_id, {})
            existing.update(
                {
                    "job_id": job_id,
                    "organisation_id": organisation_id,
                    "status": "failed",
                    "result": None,
                    "error": str(exc),
                }
            )
            _JOB_STORE[job_id] = existing


async def on_startup(ctx: dict[str, Any]) -> None:
    """Worker startup hook."""
    ctx["started"] = True


async def on_shutdown(ctx: dict[str, Any]) -> None:
    """Worker shutdown hook."""
    ctx.clear()


class WorkerSettings:
    """ARQ worker settings."""

    functions = [summarise_job]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 10
    job_timeout = 300
    keep_result = 3600
    on_startup = on_startup
    on_shutdown = on_shutdown
