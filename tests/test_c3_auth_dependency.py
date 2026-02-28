"""
Task C3 Validation: auth dependency tests.
"""

import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest
from fastapi import HTTPException
from sqlalchemy import event, text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def sqlite_env(monkeypatch):
    """Override environment for auth dependency tests."""
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("JWT_SECRET", "a" * 32)
    monkeypatch.setenv("DEBUG", "false")

    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _prepare_schema():
    """Reload DB and create schema with FK enforcement enabled."""
    import app.core.database as db

    db = importlib.reload(db)

    @event.listens_for(db.engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):  # noqa: ANN001, ARG001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    from app.models import Base, Organisation, User  # noqa: F401

    async with db.engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys=ON"))
        await conn.run_sync(Base.metadata.create_all)

    return db, Organisation, User


@pytest.mark.asyncio
async def test_valid_token_returns_user():
    db, Organisation, User = await _prepare_schema()
    from app.core.dependencies import get_current_user
    from app.core.security import create_access_token

    async with db.AsyncSessionFactory() as session:
        org = Organisation(name="Auth Org 1", slug="auth-org-1")
        user = User(
            email="auth1@example.com",
            name="Auth One",
            google_id="auth-google-1",
            organisation=org,
            role="member",
        )
        session.add_all([org, user])
        await session.commit()
        await session.refresh(user)

        token = create_access_token(
            {
                "user_id": str(user.id),
                "organisation_id": str(org.id),
                "role": user.role.value,
            }
        )
        resolved = await get_current_user(session, f"Bearer {token}")
        assert resolved.id == user.id


@pytest.mark.asyncio
async def test_invalid_token_rejected():
    db, _, _ = await _prepare_schema()
    from app.core.dependencies import get_current_user

    async with db.AsyncSessionFactory() as session:
        with pytest.raises(HTTPException) as exc:
            await get_current_user(session, "Bearer not-a-token")
        assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_expired_token_rejected():
    db, Organisation, User = await _prepare_schema()
    from app.core.config import get_settings
    from app.core.dependencies import get_current_user

    async with db.AsyncSessionFactory() as session:
        org = Organisation(name="Auth Org 2", slug="auth-org-2")
        user = User(
            email="auth2@example.com",
            name="Auth Two",
            google_id="auth-google-2",
            organisation=org,
            role="member",
        )
        session.add_all([org, user])
        await session.commit()
        await session.refresh(user)

        payload = {
            "user_id": str(user.id),
            "organisation_id": str(org.id),
            "role": user.role.value,
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        }
        token = jwt.encode(payload, get_settings().jwt_secret, algorithm="HS256")

        with pytest.raises(HTTPException) as exc:
            await get_current_user(session, f"Bearer {token}")
        assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_missing_token_rejected():
    db, _, _ = await _prepare_schema()
    from app.core.dependencies import get_current_user

    async with db.AsyncSessionFactory() as session:
        with pytest.raises(HTTPException) as exc:
            await get_current_user(session, None)
        assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_user_not_found_rejected():
    db, Organisation, User = await _prepare_schema()
    from app.core.dependencies import get_current_user
    from app.core.security import create_access_token

    async with db.AsyncSessionFactory() as session:
        org = Organisation(name="Auth Org 3", slug="auth-org-3")
        user = User(
            email="auth3@example.com",
            name="Auth Three",
            google_id="auth-google-3",
            organisation=org,
            role="admin",
        )
        session.add_all([org, user])
        await session.commit()
        await session.refresh(user)

        user_id = str(user.id)
        await session.delete(user)
        await session.commit()

        token = create_access_token(
            {
                "user_id": user_id,
                "organisation_id": str(org.id),
                "role": "admin",
            }
        )

        with pytest.raises(HTTPException) as exc:
            await get_current_user(session, f"Bearer {token}")
        assert exc.value.status_code == 401
