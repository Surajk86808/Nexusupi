"""
Product analysis routes.
"""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.credit_transaction import CreditTransaction
from app.models.user import User
from app.services.credit_service import InsufficientCreditsError, deduct_credits

router = APIRouter(prefix="/api", tags=["product"])

ANALYSIS_COST = 25
SUMMARISE_COST = 10
_JOB_STORE: dict[str, dict] = {}
_JOB_LOCK = asyncio.Lock()
_ARQ_POOL: ArqRedis | None = None
_ARQ_POOL_LOCK = asyncio.Lock()


class AnalyseRequest(BaseModel):
    text: str = Field(min_length=10, max_length=2000)


class SummariseRequest(BaseModel):
    text: str = Field(min_length=10, max_length=2000)


async def _get_arq_pool() -> ArqRedis:
    """Return a cached ARQ Redis pool."""
    global _ARQ_POOL
    if _ARQ_POOL is not None:
        return _ARQ_POOL

    async with _ARQ_POOL_LOCK:
        if _ARQ_POOL is None:
            settings = get_settings()
            _ARQ_POOL = await create_pool(
                RedisSettings.from_dsn(settings.redis_url)
            )
    return _ARQ_POOL


@router.post("/analyse")
async def analyse_text(
    payload: AnalyseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Run mock analysis after deducting credits."""
    try:
        await deduct_credits(
            db=db,
            organisation_id=current_user.organisation_id,
            user_id=current_user.id,
            amount=ANALYSIS_COST,
            reason="analysis_call",
        )
    except InsufficientCreditsError:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Insufficient credits",
        )

    words = len(payload.text.split())
    chars = len(payload.text)
    result = f"Word count: {words}, Character count: {chars}"

    remaining = (
        await db.execute(
            select(func.coalesce(func.sum(CreditTransaction.amount), 0)).where(
                CreditTransaction.organisation_id == current_user.organisation_id
            )
        )
    ).scalar_one()

    return {"result": result, "credits_remaining": int(remaining or 0)}


@router.post("/summarise")
async def summarise_text(
    payload: SummariseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Create async summarisation job after deducting credits."""
    try:
        await deduct_credits(
            db=db,
            organisation_id=current_user.organisation_id,
            user_id=current_user.id,
            amount=SUMMARISE_COST,
            reason="summarise_call",
        )
    except InsufficientCreditsError:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Insufficient credits",
        )

    job_id = str(uuid4())
    async with _JOB_LOCK:
        _JOB_STORE[job_id] = {
            "job_id": job_id,
            "organisation_id": str(current_user.organisation_id),
            "status": "pending",
            "result": None,
            "error": None,
        }
    try:
        arq_pool = await _get_arq_pool()
        await arq_pool.enqueue_job(
            "summarise_job",
            job_id,
            str(current_user.organisation_id),
            payload.text,
            _job_id=job_id,
        )
    except Exception:
        # Fail-open: keep request successful even if Redis/ARQ is unavailable.
        pass

    return {"job_id": job_id, "status": "pending"}


@router.get("/jobs/{job_id}")
async def get_job_status(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return status/result metadata for an async job."""
    async with _JOB_LOCK:
        job = _JOB_STORE.get(str(job_id))

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    if str(job.get("organisation_id")) != str(current_user.organisation_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant mismatch",
        )

    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "result": job.get("result"),
        "error": job.get("error"),
    }
