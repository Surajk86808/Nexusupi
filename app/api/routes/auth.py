"""
Authentication routes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.dependencies import get_current_user
from app.models.user import User

router = APIRouter(tags=["auth"])


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)) -> dict:
    """Return authenticated user profile information."""
    return {
        "user_id": current_user.id,
        "email": current_user.email,
        "name": current_user.name,
        "organisation_id": current_user.organisation_id,
        "role": current_user.role.value if hasattr(current_user.role, "value") else current_user.role,
    }
