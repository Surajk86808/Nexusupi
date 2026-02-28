"""
Task C2 Validation: JWT security tests.
"""

from datetime import datetime, timedelta, timezone
import sys
from pathlib import Path

import jwt
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def jwt_env(monkeypatch):
    """Set minimum environment for security module tests."""
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("JWT_SECRET", "a" * 32)
    monkeypatch.setenv("DEBUG", "false")

    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _base_payload() -> dict:
    return {
        "user_id": "8d8e2571-8b90-4b1a-97e1-5297f8ca8f8a",
        "organisation_id": "2f8ee07d-beab-4f0f-9fa0-091d9dc97ea5",
        "role": "member",
    }


def test_token_creation_works():
    from app.core.security import create_access_token

    token = create_access_token(_base_payload())
    assert isinstance(token, str)
    assert len(token) > 20


def test_token_verification_works():
    from app.core.security import create_access_token, verify_access_token

    payload = _base_payload()
    token = create_access_token(payload)
    decoded = verify_access_token(token)

    assert decoded["user_id"] == payload["user_id"]
    assert decoded["organisation_id"] == payload["organisation_id"]
    assert decoded["role"] == payload["role"]
    assert "exp" in decoded


def test_expiry_enforcement_works():
    from app.core.config import get_settings
    from app.core.security import TokenValidationError, verify_access_token

    expired_payload = {
        **_base_payload(),
        "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
    }
    token = jwt.encode(expired_payload, get_settings().jwt_secret, algorithm="HS256")

    with pytest.raises(TokenValidationError):
        verify_access_token(token)


def test_tampered_token_rejected():
    from app.core.security import TokenValidationError, create_access_token, verify_access_token

    token = create_access_token(_base_payload())
    tampered = f"{token}tampered"

    with pytest.raises(TokenValidationError):
        verify_access_token(tampered)


def test_invalid_token_rejected():
    from app.core.security import TokenValidationError, verify_access_token

    with pytest.raises(TokenValidationError):
        verify_access_token("not-a-valid-jwt")
