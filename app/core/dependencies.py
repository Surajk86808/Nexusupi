"""
FastAPI authentication dependencies.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import TokenValidationError, verify_access_token
from app.models.user import User


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> User:
    """
    Resolve currently authenticated user from Authorization Bearer token.
    """
    if not authorization:
        raise _unauthorized("Missing authorization header")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _unauthorized("Invalid authorization header")

    try:
        payload = verify_access_token(token)
        user_id = UUID(str(payload.get("user_id", "")))
    except (TokenValidationError, ValueError):
        raise _unauthorized("Invalid or expired token")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise _unauthorized("User not found")

    token_org_id = payload.get("organisation_id")
    if token_org_id is not None and str(user.organisation_id) != str(token_org_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant mismatch",
        )

    return user
