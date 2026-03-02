"""
Product analysis routes.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.credit_transaction import CreditTransaction
from app.models.user import User
from app.services.credit_service import (
    IDEMPOTENCY_TTL_HOURS,
    DeductionResult,
    InsufficientCreditsError,
    deduct_credits,
)

router = APIRouter(prefix="/api", tags=["product"])

ANALYSIS_COST = 25
SUMMARISE_COST = 10
_JOB_STORE: dict[str, dict] = {}
_JOB_LOCK = asyncio.Lock()
_ARQ_POOL: ArqRedis | None = None
_ARQ_POOL_LOCK = asyncio.Lock()
_IDEMPOTENCY_STORE: dict[str, dict] = {}
_IDEMPOTENCY_LOCK = asyncio.Lock()


class AnalyseRequest(BaseModel):
    text: str = Field(min_length=10, max_length=2000)


class SummariseRequest(BaseModel):
    text: str = Field(min_length=10, max_length=2000)


def _idempotency_store_key(organisation_id: str, endpoint: str, key: str) -> str:
    return f"{organisation_id}:{endpoint}:{key}"


async def _get_cached_idempotent_response(
    organisation_id: str,
    endpoint: str,
    idempotency_key: str | None,
) -> dict | None:
    if not idempotency_key:
        return None

    now = datetime.now(timezone.utc)
    cache_key = _idempotency_store_key(organisation_id, endpoint, idempotency_key)
    async with _IDEMPOTENCY_LOCK:
        cached = _IDEMPOTENCY_STORE.get(cache_key)
        if not cached:
            return None
        if cached["expires_at"] < now:
            _IDEMPOTENCY_STORE.pop(cache_key, None)
            return None
        return cached["response"]


async def _cache_idempotent_response(
    organisation_id: str,
    endpoint: str,
    idempotency_key: str | None,
    response_payload: dict,
) -> None:
    if not idempotency_key:
        return
    cache_key = _idempotency_store_key(organisation_id, endpoint, idempotency_key)
    async with _IDEMPOTENCY_LOCK:
        _IDEMPOTENCY_STORE[cache_key] = {
            "response": response_payload,
            "expires_at": datetime.now(timezone.utc) + timedelta(hours=IDEMPOTENCY_TTL_HOURS),
        }


async def _get_arq_pool() -> ArqRedis:
    """Return a cached ARQ Redis pool."""
    global _ARQ_POOL
    if _ARQ_POOL is not None:
        return _ARQ_POOL

    async with _ARQ_POOL_LOCK:
        if _ARQ_POOL is None:
            settings = get_settings()
            _ARQ_POOL = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return _ARQ_POOL


@router.post("/analyse")
async def analyse_text(
    payload: AnalyseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    """Run mock analysis after deducting credits."""
    org_id = str(current_user.organisation_id)
    cached = await _get_cached_idempotent_response(org_id, "analyse", idempotency_key)
    if cached is not None:
        return cached

    try:
        deduction = await deduct_credits(
            db=db,
            organisation_id=current_user.organisation_id,
            user_id=current_user.id,
            amount=ANALYSIS_COST,
            reason="analysis_call",
            idempotency_key=idempotency_key,
            include_status=True,
        )
    except InsufficientCreditsError:
        current_balance = (
            await db.execute(
                select(func.coalesce(func.sum(CreditTransaction.amount), 0)).where(
                    CreditTransaction.organisation_id == current_user.organisation_id
                )
            )
        ).scalar_one()
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "insufficient_credits",
                "balance": int(current_balance or 0),
                "required": ANALYSIS_COST,
            },
        )

    if isinstance(deduction, DeductionResult) and deduction.reused:
        cached = await _get_cached_idempotent_response(org_id, "analyse", idempotency_key)
        if cached is not None:
            return cached

    words = payload.text.split()
    word_count = len(words)
    unique_words = len({w.lower().strip(".,!?;:") for w in words if w.strip(".,!?;:")})
    char_count = len(payload.text)
    result = (
        f"Analysis complete. Word count: {word_count}. "
        f"Unique words: {unique_words}. Character count: {char_count}."
    )

    remaining = (
        await db.execute(
            select(func.coalesce(func.sum(CreditTransaction.amount), 0)).where(
                CreditTransaction.organisation_id == current_user.organisation_id
            )
        )
    ).scalar_one()

    response_payload = {"result": result, "credits_remaining": int(remaining or 0)}
    await _cache_idempotent_response(org_id, "analyse", idempotency_key, response_payload)
    return response_payload


@router.post("/summarise")
async def summarise_text(
    payload: SummariseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    """Create async summarisation job after deducting credits."""
    org_id = str(current_user.organisation_id)
    cached = await _get_cached_idempotent_response(org_id, "summarise", idempotency_key)
    if cached is not None:
        return cached

    try:
        deduction = await deduct_credits(
            db=db,
            organisation_id=current_user.organisation_id,
            user_id=current_user.id,
            amount=SUMMARISE_COST,
            reason="summarise_call",
            idempotency_key=idempotency_key,
            include_status=True,
        )
    except InsufficientCreditsError:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Insufficient credits",
        )

    if isinstance(deduction, DeductionResult) and deduction.reused:
        cached = await _get_cached_idempotent_response(org_id, "summarise", idempotency_key)
        if cached is not None:
            return cached

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
        arq_pool = await asyncio.wait_for(_get_arq_pool(), timeout=0.5)
        await asyncio.wait_for(
            arq_pool.enqueue_job(
                "summarise_job",
                job_id,
                org_id,
                payload.text,
                _job_id=job_id,
            ),
            timeout=0.5,
        )
        response_payload = {"job_id": job_id, "status": "pending"}
    except Exception as exc:
        async with _JOB_LOCK:
            existing = _JOB_STORE.get(job_id, {})
            existing.update(
                {
                    "job_id": job_id,
                    "organisation_id": org_id,
                    "status": "pending",
                    "result": None,
                    "error": f"enqueue_failed: {exc.__class__.__name__}",
                }
            )
            _JOB_STORE[job_id] = existing
        response_payload = {"job_id": job_id, "status": "pending"}

    await _cache_idempotent_response(org_id, "summarise", idempotency_key, response_payload)
    return response_payload


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
