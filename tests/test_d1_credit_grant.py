"""
Task D1 Validation: credit grant endpoint tests.
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
    """Configure isolated SQLite DB for credit grant endpoint tests."""
    db_path = tmp_path / "test_d1_credit_grant.db"
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
async def test_admin_can_grant_credits():
    from app.core.security import create_access_token

    app, db, Organisation, User, CreditTransaction = await _prepare_app_and_db()

    async with db.AsyncSessionFactory() as session:
        org = Organisation(name="D1 Org A", slug="d1-org-a")
        admin = User(
            email="d1-admin@example.com",
            name="D1 Admin",
            google_id="d1-google-admin",
            organisation=org,
            role="admin",
        )
        session.add_all([org, admin])
        await session.commit()
        await session.refresh(admin)

    token = create_access_token(
        {
            "user_id": str(admin.id),
            "organisation_id": str(admin.organisation_id),
            "role": "admin",
        }
    )

    with TestClient(app) as client:
        response = client.post(
            "/credits/grant",
            headers={"Authorization": f"Bearer {token}"},
            json={"amount": 100, "reason": "manual grant"},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "success"}

    async with db.AsyncSessionFactory() as session:
        count = (
            await session.execute(select(func.count(CreditTransaction.id)))
        ).scalar_one()
        assert count == 1


@pytest.mark.asyncio
async def test_non_admin_rejected_403():
    from app.core.security import create_access_token

    app, db, Organisation, User, _ = await _prepare_app_and_db()

    async with db.AsyncSessionFactory() as session:
        org = Organisation(name="D1 Org B", slug="d1-org-b")
        member = User(
            email="d1-member@example.com",
            name="D1 Member",
            google_id="d1-google-member",
            organisation=org,
            role="member",
        )
        session.add_all([org, member])
        await session.commit()
        await session.refresh(member)

    token = create_access_token(
        {
            "user_id": str(member.id),
            "organisation_id": str(member.organisation_id),
            "role": "member",
        }
    )

    with TestClient(app) as client:
        response = client.post(
            "/credits/grant",
            headers={"Authorization": f"Bearer {token}"},
            json={"amount": 50, "reason": "should fail"},
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_transaction_created_correctly():
    from app.core.security import create_access_token

    app, db, Organisation, User, CreditTransaction = await _prepare_app_and_db()

    async with db.AsyncSessionFactory() as session:
        org = Organisation(name="D1 Org C", slug="d1-org-c")
        admin = User(
            email="d1-admin-c@example.com",
            name="D1 Admin C",
            google_id="d1-google-admin-c",
            organisation=org,
            role="admin",
        )
        session.add_all([org, admin])
        await session.commit()
        await session.refresh(admin)

    token = create_access_token(
        {
            "user_id": str(admin.id),
            "organisation_id": str(admin.organisation_id),
            "role": "admin",
        }
    )

    with TestClient(app) as client:
        response = client.post(
            "/credits/grant",
            headers={"Authorization": f"Bearer {token}"},
            json={"amount": 175, "reason": "seed credits"},
        )
    assert response.status_code == 200

    async with db.AsyncSessionFactory() as session:
        row = (
            await session.execute(select(CreditTransaction))
        ).scalar_one()
        assert row.organisation_id == admin.organisation_id
        assert row.user_id == admin.id
        assert row.amount == 175
        assert row.reason == "seed credits"


@pytest.mark.asyncio
async def test_ledger_integrity_maintained():
    from app.core.security import create_access_token

    app, db, Organisation, User, CreditTransaction = await _prepare_app_and_db()

    async with db.AsyncSessionFactory() as session:
        org = Organisation(name="D1 Org D", slug="d1-org-d")
        admin = User(
            email="d1-admin-d@example.com",
            name="D1 Admin D",
            google_id="d1-google-admin-d",
            organisation=org,
            role="admin",
        )
        session.add_all([org, admin])
        await session.commit()
        await session.refresh(admin)

    token = create_access_token(
        {
            "user_id": str(admin.id),
            "organisation_id": str(admin.organisation_id),
            "role": "admin",
        }
    )

    with TestClient(app) as client:
        r1 = client.post(
            "/credits/grant",
            headers={"Authorization": f"Bearer {token}"},
            json={"amount": 100, "reason": "grant 1"},
        )
        r2 = client.post(
            "/credits/grant",
            headers={"Authorization": f"Bearer {token}"},
            json={"amount": 30, "reason": "grant 2"},
        )
    assert r1.status_code == 200
    assert r2.status_code == 200

    async with db.AsyncSessionFactory() as session:
        rows = (
            await session.execute(select(CreditTransaction).order_by(CreditTransaction.created_at))
        ).scalars().all()
        assert len(rows) == 2
        assert rows[0].amount == 100
        assert rows[1].amount == 30

        total = (
            await session.execute(
                select(func.sum(CreditTransaction.amount)).where(
                    CreditTransaction.organisation_id == admin.organisation_id
                )
            )
        ).scalar_one()
        assert total == 130
