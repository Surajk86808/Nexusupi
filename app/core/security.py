"""
JWT token creation and verification utilities.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from jwt import ExpiredSignatureError, InvalidTokenError

from app.core.config import get_settings

ACCESS_TOKEN_EXPIRE_HOURS = 24


class TokenValidationError(Exception):
    """Raised when a JWT cannot be validated."""


def create_access_token(data: dict[str, Any]) -> str:
    """
    Create a signed JWT access token with 24-hour expiry.
    """
    settings = get_settings()
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.jwt_secret, algorithm="HS256")


def verify_access_token(token: str) -> dict[str, Any]:
    """
    Verify JWT signature and expiry, returning decoded payload.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            options={"require": ["exp"]},
        )
        return payload
    except ExpiredSignatureError as exc:
        raise TokenValidationError("Token has expired") from exc
    except InvalidTokenError as exc:
        raise TokenValidationError("Invalid token") from exc
