"""
Credit ledger service operations.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credit_transaction import CreditTransaction


class InsufficientCreditsError(Exception):
    """Raised when an organisation does not have enough credits."""


_ORG_LOCKS: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


async def deduct_credits(
    db: AsyncSession,
    organisation_id: UUID,
    user_id: UUID,
    amount: int,
    reason: str,
    idempotency_key: str | None = None,
) -> CreditTransaction:
    """
    Atomically deduct credits by appending a negative ledger transaction.
    """
    if amount <= 0:
        raise ValueError("amount must be positive")

    # In-process lock protects SQLite tests and same-process concurrency;
    # row-level locks below provide DB-level safety for supported backends.
    async with _ORG_LOCKS[str(organisation_id)]:
        tx_ctx = db.begin_nested() if db.in_transaction() else db.begin()
        async with tx_ctx:
            if idempotency_key:
                existing = (
                    await db.execute(
                        select(CreditTransaction).where(
                            CreditTransaction.idempotency_key == idempotency_key
                        )
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    return existing

            await db.execute(
                select(CreditTransaction.id)
                .where(CreditTransaction.organisation_id == organisation_id)
                .with_for_update()
            )

            current_balance = (
                await db.execute(
                    select(func.coalesce(func.sum(CreditTransaction.amount), 0)).where(
                        CreditTransaction.organisation_id == organisation_id
                    )
                )
            ).scalar_one()

            if int(current_balance or 0) < amount:
                raise InsufficientCreditsError("Insufficient credits")

            txn = CreditTransaction(
                organisation_id=organisation_id,
                user_id=user_id,
                amount=-amount,
                reason=reason,
                idempotency_key=idempotency_key,
            )
            db.add(txn)
            await db.flush()
            return txn
