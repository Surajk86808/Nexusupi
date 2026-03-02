"""
ARQ worker configuration and job handlers.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from arq.connections import RedisSettings
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import AsyncSessionFactory
from app.models.job import Job

settings = get_settings()


def _build_redis_settings() -> RedisSettings:
    url = settings.redis_url
    if url.startswith("rediss://"):
        # Parse rediss:// URL manually for ARQ TLS support
        without_scheme = url.replace("rediss://", "")
        if "@" in without_scheme:
            auth_part, host_part = without_scheme.rsplit("@", 1)
            password = auth_part.split(":", 1)[1] if ":" in auth_part else auth_part
            host = host_part.split(":")[0]
            port = int(host_part.split(":")[1]) if ":" in host_part else 6379
        else:
            password = None
            host = without_scheme.split(":")[0]
            port = 6379
        return RedisSettings(
            host=host,
            port=port,
            password=password,
            ssl=True,
        )
    return RedisSettings.from_dsn(url)


async def summarise_job(ctx: dict[str, Any], job_id: str, organisation_id: str, text: str) -> None:
    """Process summarisation jobs and persist status/result in database."""
    session_factory = ctx.get("db_factory", AsyncSessionFactory)
    parsed_job_id = UUID(job_id)
    parsed_org_id = UUID(organisation_id)
    try:
        async with session_factory() as session:
            async with session.begin():
                job = (
                    await session.execute(
                        select(Job).where(
                            Job.id == parsed_job_id,
                            Job.organisation_id == parsed_org_id,
                        )
                    )
                ).scalar_one_or_none()
                if job is None:
                    return
                job.status = "running"
                job.error = None
            await session.commit()

        summary = f"Summary: {len(text.split())} words processed."
        async with session_factory() as session:
            async with session.begin():
                job = (
                    await session.execute(
                        select(Job).where(
                            Job.id == parsed_job_id,
                            Job.organisation_id == parsed_org_id,
                        )
                    )
                ).scalar_one_or_none()
                if job is None:
                    return
                job.status = "completed"
                job.result = summary
                job.error = None
            await session.commit()
    except Exception as exc:
        async with session_factory() as session:
            async with session.begin():
                job = (
                    await session.execute(
                        select(Job).where(
                            Job.id == parsed_job_id,
                            Job.organisation_id == parsed_org_id,
                        )
                    )
                ).scalar_one_or_none()
                if job is not None:
                    job.status = "failed"
                    job.result = None
                    job.error = str(exc)
            await session.commit()


async def on_startup(ctx: dict[str, Any]) -> None:
    """Worker startup hook."""
    ctx["started"] = True
    ctx["db_factory"] = AsyncSessionFactory


async def on_shutdown(ctx: dict[str, Any]) -> None:
    """Worker shutdown hook."""
    ctx.clear()


class WorkerSettings:
    """ARQ worker settings."""

    functions = [summarise_job]
    redis_settings = _build_redis_settings()
    max_jobs = 10
    job_timeout = 300
    keep_result = 3600
    on_startup = on_startup
    on_shutdown = on_shutdown
