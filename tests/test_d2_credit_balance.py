"""
Task D2 Validation: credit balance endpoint tests.
"""

import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def sqlite_env(monkeypatch, tmp_path):
    """Configure isolated SQLite DB for balance endpoint tests."""
    db_path = tmp_path / "test_d2_credit_balance.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("JWT_SECRET", "a" * 32)
    monkeypatch.setenv("DEBUG", "false")

    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _prepare_app_and_db():
    """Create schema and app with DB dependency override."""
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
async def test_correct_balance_calculation():
    from app.core.security import create_access_token

    app, db, Organisation, User, CreditTransaction = await _prepare_app_and_db()
    async with db.AsyncSessionFactory() as session:
        org = Organisation(name="D2 Org A", slug="d2-org-a")
        user = User(
            email="d2a@example.com",
            name="D2 A",
            google_id="d2-google-a",
            organisation=org,
            role="admin",
        )
        session.add_all([org, user])
        await session.flush()
        session.add_all(
            [
                CreditTransaction(organisation_id=org.id, user_id=user.id, amount=100, reason="add"),
                CreditTransaction(organisation_id=org.id, user_id=user.id, amount=-40, reason="use"),
            ]
        )
        await session.commit()
        await session.refresh(user)

    token = create_access_token(
        {"user_id": str(user.id), "organisation_id": str(user.organisation_id), "role": "admin"}
    )
    with TestClient(app) as client:
        response = client.get("/credits/balance", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["balance"] == 60


@pytest.mark.asyncio
async def test_correct_transaction_listing():
    from app.core.security import create_access_token

    app, db, Organisation, User, CreditTransaction = await _prepare_app_and_db()
    async with db.AsyncSessionFactory() as session:
        org = Organisation(name="D2 Org B", slug="d2-org-b")
        user = User(
            email="d2b@example.com",
            name="D2 B",
            google_id="d2-google-b",
            organisation=org,
            role="member",
        )
        session.add_all([org, user])
        await session.flush()

        base_ts = datetime.now(timezone.utc)
        for i in range(12):
            session.add(
                CreditTransaction(
                    organisation_id=org.id,
                    user_id=user.id,
                    amount=i + 1,
                    reason=f"txn-{i + 1}",
                    created_at=base_ts + timedelta(seconds=i),
                )
            )
        await session.commit()
        await session.refresh(user)

    token = create_access_token(
        {"user_id": str(user.id), "organisation_id": str(user.organisation_id), "role": "member"}
    )
    with TestClient(app) as client:
        response = client.get("/credits/balance", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    transactions = response.json()["transactions"]
    assert len(transactions) == 10
    assert transactions[0]["reason"] == "txn-12"
    assert transactions[-1]["reason"] == "txn-3"


@pytest.mark.asyncio
async def test_organisation_isolation_enforced():
    from app.core.security import create_access_token

    app, db, Organisation, User, CreditTransaction = await _prepare_app_and_db()
    async with db.AsyncSessionFactory() as session:
        org_a = Organisation(name="D2 Org C", slug="d2-org-c")
        org_b = Organisation(name="D2 Org D", slug="d2-org-d")
        user_a = User(
            email="d2c@example.com",
            name="D2 C",
            google_id="d2-google-c",
            organisation=org_a,
            role="member",
        )
        user_b = User(
            email="d2d@example.com",
            name="D2 D",
            google_id="d2-google-d",
            organisation=org_b,
            role="member",
        )
        session.add_all([org_a, org_b, user_a, user_b])
        await session.flush()
        session.add_all(
            [
                CreditTransaction(organisation_id=org_a.id, user_id=user_a.id, amount=10, reason="a"),
                CreditTransaction(organisation_id=org_b.id, user_id=user_b.id, amount=200, reason="b"),
            ]
        )
        await session.commit()
        await session.refresh(user_a)

    token = create_access_token(
        {"user_id": str(user_a.id), "organisation_id": str(user_a.organisation_id), "role": "member"}
    )
    with TestClient(app) as client:
        response = client.get("/credits/balance", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["balance"] == 10
    assert len(body["transactions"]) == 1
    assert body["transactions"][0]["reason"] == "a"


@pytest.mark.asyncio
async def test_empty_ledger_returns_balance_zero():
    from app.core.security import create_access_token

    app, db, Organisation, User, _ = await _prepare_app_and_db()
    async with db.AsyncSessionFactory() as session:
        org = Organisation(name="D2 Org E", slug="d2-org-e")
        user = User(
            email="d2e@example.com",
            name="D2 E",
            google_id="d2-google-e",
            organisation=org,
            role="admin",
        )
        session.add_all([org, user])
        await session.commit()
        await session.refresh(user)

    token = create_access_token(
        {"user_id": str(user.id), "organisation_id": str(user.organisation_id), "role": "admin"}
    )
    with TestClient(app) as client:
        response = client.get("/credits/balance", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["balance"] == 0
    assert response.json()["transactions"] == []


@pytest.mark.asyncio
async def test_multiple_transactions_summed_correctly():
    from app.core.security import create_access_token

    app, db, Organisation, User, CreditTransaction = await _prepare_app_and_db()
    async with db.AsyncSessionFactory() as session:
        org = Organisation(name="D2 Org F", slug="d2-org-f")
        user = User(
            email="d2f@example.com",
            name="D2 F",
            google_id="d2-google-f",
            organisation=org,
            role="admin",
        )
        session.add_all([org, user])
        await session.flush()
        for amount in [500, -120, -80, 40, -10]:
            session.add(
                CreditTransaction(
                    organisation_id=org.id,
                    user_id=user.id,
                    amount=amount,
                    reason=f"amt-{amount}",
                )
            )
        await session.commit()
        await session.refresh(user)

    token = create_access_token(
        {"user_id": str(user.id), "organisation_id": str(user.organisation_id), "role": "admin"}
    )
    with TestClient(app) as client:
        response = client.get("/credits/balance", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["balance"] == 330

    async with db.AsyncSessionFactory() as session:
        all_rows = (await session.execute(select(CreditTransaction))).scalars().all()
        assert len(all_rows) == 5
