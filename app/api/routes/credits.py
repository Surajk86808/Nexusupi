"""
Credit ledger routes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.credit_transaction import CreditTransaction
from app.models.user import User

router = APIRouter(prefix="/credits", tags=["credits"])


class GrantCreditsRequest(BaseModel):
    amount: int = Field(gt=0)
    reason: str


@router.post("/grant")
async def grant_credits(
    payload: GrantCreditsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Grant credits by appending a positive ledger transaction."""
    role_value = current_user.role.value if hasattr(current_user.role, "value") else current_user.role
    if role_value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    txn = CreditTransaction(
        organisation_id=current_user.organisation_id,
        user_id=current_user.id,
        amount=payload.amount,
        reason=payload.reason,
    )
    db.add(txn)
    await db.commit()

    return {"status": "success"}


@router.get("/balance")
async def get_credit_balance(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return organisation balance derived from ledger and recent transactions."""
    balance_query = select(func.coalesce(func.sum(CreditTransaction.amount), 0)).where(
        CreditTransaction.organisation_id == current_user.organisation_id
    )
    balance = (await db.execute(balance_query)).scalar_one()

    tx_query = (
        select(CreditTransaction)
        .where(CreditTransaction.organisation_id == current_user.organisation_id)
        .order_by(CreditTransaction.created_at.desc())
        .limit(10)
    )
    transactions = (await db.execute(tx_query)).scalars().all()

    return {
        "balance": int(balance or 0),
        "transactions": [
            {
                "id": txn.id,
                "amount": txn.amount,
                "reason": txn.reason,
                "created_at": txn.created_at,
            }
            for txn in transactions
        ],
    }
