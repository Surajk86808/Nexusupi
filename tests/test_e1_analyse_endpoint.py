"""
Task E1 Validation: /api/analyse credit-gated endpoint tests.
"""

import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def sqlite_env(monkeypatch, tmp_path):
    """Configure isolated SQLite DB for analysis endpoint tests."""
    db_path = tmp_path / "test_e1_analyse.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("JWT_SECRET", "a" * 32)
    monkeypatch.setenv("DEBUG", "false")

    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _prepare_app_and_db():
    """Create schema and FastAPI app with DB dependency override."""
    import app.core.database as db

    db = importlib.reload(db)

    from app.core.database import get_db
    from app.main import create_app
    from app.models import Base, CreditTransaction, Organisation, User

    async with db.engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys=ON"))
        await conn.run_sync(Base.metadata.create_all)

    app = create_app()

    async def override_get_db():
        async with db.AsyncSessionFactory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    return app, db, Organisation, User, CreditTransaction


@pytest.mark.asyncio
async def test_successful_analysis_with_credits():
    from app.core.security import create_access_token

    app, db, Organisation, User, CreditTransaction = await _prepare_app_and_db()
    async with db.AsyncSessionFactory() as session:
        org = Organisation(name="E1 Org A", slug="e1-org-a")
        user = User(
            email="e1a@example.com",
            name="E1 A",
            google_id="e1-google-a",
            organisation=org,
            role="admin",
        )
        session.add_all([org, user])
        await session.flush()
        session.add(
            CreditTransaction(organisation_id=org.id, user_id=user.id, amount=100, reason="seed")
        )
        await session.commit()
        await session.refresh(user)

    token = create_access_token(
        {"user_id": str(user.id), "organisation_id": str(user.organisation_id), "role": "admin"}
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/analyse",
            headers={"Authorization": f"Bearer {token}"},
            json={"text": "This is a valid analysis input text."},
        )

    assert response.status_code == 200
    body = response.json()
    assert "Word count:" in body["result"]
    assert "Character count:" in body["result"]
    assert body["credits_remaining"] == 75


@pytest.mark.asyncio
async def test_insufficient_credits_rejected():
    from app.core.security import create_access_token

    app, db, Organisation, User, CreditTransaction = await _prepare_app_and_db()
    async with db.AsyncSessionFactory() as session:
        org = Organisation(name="E1 Org B", slug="e1-org-b")
        user = User(
            email="e1b@example.com",
            name="E1 B",
            google_id="e1-google-b",
            organisation=org,
            role="member",
        )
        session.add_all([org, user])
        await session.flush()
        session.add(
            CreditTransaction(organisation_id=org.id, user_id=user.id, amount=10, reason="seed")
        )
        await session.commit()
        await session.refresh(user)

    token = create_access_token(
        {"user_id": str(user.id), "organisation_id": str(user.organisation_id), "role": "member"}
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/analyse",
            headers={"Authorization": f"Bearer {token}"},
            json={"text": "This input is long enough but credits are low."},
        )

    assert response.status_code == 402


@pytest.mark.asyncio
async def test_credit_deducted_correctly():
    from app.core.security import create_access_token

    app, db, Organisation, User, CreditTransaction = await _prepare_app_and_db()
    async with db.AsyncSessionFactory() as session:
        org = Organisation(name="E1 Org C", slug="e1-org-c")
        user = User(
            email="e1c@example.com",
            name="E1 C",
            google_id="e1-google-c",
            organisation=org,
            role="admin",
        )
        session.add_all([org, user])
        await session.flush()
        session.add(
            CreditTransaction(organisation_id=org.id, user_id=user.id, amount=60, reason="seed")
        )
        await session.commit()
        await session.refresh(user)

    token = create_access_token(
        {"user_id": str(user.id), "organisation_id": str(user.organisation_id), "role": "admin"}
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/analyse",
            headers={"Authorization": f"Bearer {token}"},
            json={"text": "The endpoint should deduct twenty five credits."},
        )
    assert response.status_code == 200
    assert response.json()["credits_remaining"] == 35

    async with db.AsyncSessionFactory() as session:
        total = (
            await session.execute(
                select(func.coalesce(func.sum(CreditTransaction.amount), 0)).where(
                    CreditTransaction.organisation_id == user.organisation_id
                )
            )
        ).scalar_one()
        assert total == 35


@pytest.mark.asyncio
async def test_tenant_isolation_enforced():
    from app.core.security import create_access_token

    app, db, Organisation, User, CreditTransaction = await _prepare_app_and_db()
    async with db.AsyncSessionFactory() as session:
        org_a = Organisation(name="E1 Org D", slug="e1-org-d")
        org_b = Organisation(name="E1 Org E", slug="e1-org-e")
        user_a = User(
            email="e1d@example.com",
            name="E1 D",
            google_id="e1-google-d",
            organisation=org_a,
            role="member",
        )
        user_b = User(
            email="e1e@example.com",
            name="E1 E",
            google_id="e1-google-e",
            organisation=org_b,
            role="admin",
        )
        session.add_all([org_a, org_b, user_a, user_b])
        await session.flush()
        session.add_all(
            [
                CreditTransaction(organisation_id=org_a.id, user_id=user_a.id, amount=100, reason="seed-a"),
                CreditTransaction(organisation_id=org_b.id, user_id=user_b.id, amount=500, reason="seed-b"),
            ]
        )
        await session.commit()
        await session.refresh(user_a)

    token = create_access_token(
        {"user_id": str(user_a.id), "organisation_id": str(user_a.organisation_id), "role": "member"}
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/analyse",
            headers={"Authorization": f"Bearer {token}"},
            json={"text": "Tenant isolation must keep credits scoped correctly."},
        )

    assert response.status_code == 200
    assert response.json()["credits_remaining"] == 75

    async with db.AsyncSessionFactory() as session:
        balance_a = (
            await session.execute(
                select(func.coalesce(func.sum(CreditTransaction.amount), 0)).where(
                    CreditTransaction.organisation_id == org_a.id
                )
            )
        ).scalar_one()
        balance_b = (
            await session.execute(
                select(func.coalesce(func.sum(CreditTransaction.amount), 0)).where(
                    CreditTransaction.organisation_id == org_b.id
                )
            )
        ).scalar_one()
        assert balance_a == 75
        assert balance_b == 500
