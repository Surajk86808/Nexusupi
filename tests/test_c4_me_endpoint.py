"""
Task C4 Validation: /me endpoint tests.
"""

import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def sqlite_env(monkeypatch, tmp_path):
    """Configure test environment for endpoint auth tests."""
    db_path = tmp_path / "test_c4_me_endpoint.db"

    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("JWT_SECRET", "a" * 32)
    monkeypatch.setenv("DEBUG", "false")

    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _prepare_app_and_db():
    """Create app + database schema and return test handles."""
    import app.core.database as db

    db = importlib.reload(db)

    @event.listens_for(db.engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):  # noqa: ANN001, ARG001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    from app.main import create_app
    from app.models import Base, Organisation, User
    from app.core.database import get_db

    async with db.engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys=ON"))
        await conn.run_sync(Base.metadata.create_all)

    app = create_app()

    async def override_get_db():
        async with db.AsyncSessionFactory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    return app, db, Organisation, User


@pytest.mark.asyncio
async def test_valid_jwt_returns_correct_user_info():
    from app.core.security import create_access_token

    app, db, Organisation, User = await _prepare_app_and_db()

    async with db.AsyncSessionFactory() as session:
        org = Organisation(name="C4 Org A", slug="c4-org-a")
        user = User(
            email="c4a@example.com",
            name="C4 User A",
            google_id="c4-google-a",
            organisation=org,
            role="member",
        )
        session.add_all([org, user])
        await session.commit()
        await session.refresh(user)

    token = create_access_token(
        {
            "user_id": str(user.id),
            "organisation_id": str(user.organisation_id),
            "role": "member",
        }
    )

    with TestClient(app) as client:
        response = client.get("/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == str(user.id)
    assert body["email"] == "c4a@example.com"
    assert body["name"] == "C4 User A"
    assert body["organisation_id"] == str(user.organisation_id)
    assert body["role"] == "member"


@pytest.mark.asyncio
async def test_invalid_jwt_rejected():
    app, _, _, _ = await _prepare_app_and_db()
    with TestClient(app) as client:
        response = client.get("/me", headers={"Authorization": "Bearer invalid.token.value"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_missing_jwt_rejected():
    app, _, _, _ = await _prepare_app_and_db()
    with TestClient(app) as client:
        response = client.get("/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_tenant_isolation_enforced():
    from app.core.security import create_access_token

    app, db, Organisation, User = await _prepare_app_and_db()

    async with db.AsyncSessionFactory() as session:
        org_a = Organisation(name="C4 Org B", slug="c4-org-b")
        org_b = Organisation(name="C4 Org C", slug="c4-org-c")
        user = User(
            email="c4b@example.com",
            name="C4 User B",
            google_id="c4-google-b",
            organisation=org_a,
            role="admin",
        )
        session.add_all([org_a, org_b, user])
        await session.commit()
        await session.refresh(user)
        await session.refresh(org_b)

    token = create_access_token(
        {
            "user_id": str(user.id),
            "organisation_id": str(org_b.id),  # intentional mismatch
            "role": "admin",
        }
    )

    with TestClient(app) as client:
        response = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
