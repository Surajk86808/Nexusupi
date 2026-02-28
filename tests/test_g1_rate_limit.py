"""
Task G1 Validation: organisation-level rate limiting middleware tests.
"""

import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def sqlite_env(monkeypatch, tmp_path):
    """Configure isolated SQLite DB for rate limit middleware tests."""
    db_path = tmp_path / "test_g1_rate_limit.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("JWT_SECRET", "a" * 32)
    monkeypatch.setenv("DEBUG", "false")

    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def lower_rate_limit_for_tests(monkeypatch):
    """Set low limit for deterministic fast tests and clear store each test."""
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("JWT_SECRET", "a" * 32)

    from app.core.config import get_settings

    get_settings.cache_clear()
    import app.middleware.rate_limit as rl

    monkeypatch.setattr(rl, "RATE_LIMIT_MAX_REQUESTS", 2)
    monkeypatch.setattr(rl, "RATE_LIMIT_WINDOW_SECONDS", 60)
    rl.reset_rate_limit_store()
    yield
    rl.reset_rate_limit_store()
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
async def test_requests_under_limit_succeed():
    from app.core.security import create_access_token

    app, db, Organisation, User, CreditTransaction = await _prepare_app_and_db()
    async with db.AsyncSessionFactory() as session:
        org = Organisation(name="G1 Org A", slug="g1-org-a")
        user = User(
            email="g1a@example.com",
            name="G1 A",
            google_id="g1-google-a",
            organisation=org,
            role="member",
        )
        session.add_all([org, user])
        await session.flush()
        session.add(CreditTransaction(organisation_id=org.id, user_id=user.id, amount=100, reason="seed"))
        await session.commit()
        await session.refresh(user)

    token = create_access_token(
        {"user_id": str(user.id), "organisation_id": str(user.organisation_id), "role": "member"}
    )
    payload = {"text": "This is valid analysis input for under limit check."}

    with TestClient(app) as client:
        r1 = client.post("/api/analyse", headers={"Authorization": f"Bearer {token}"}, json=payload)
        r2 = client.post("/api/analyse", headers={"Authorization": f"Bearer {token}"}, json=payload)

    assert r1.status_code == 200
    assert r2.status_code == 200


@pytest.mark.asyncio
async def test_requests_exceeding_limit_rejected_with_429():
    from app.core.security import create_access_token

    app, db, Organisation, User, CreditTransaction = await _prepare_app_and_db()
    async with db.AsyncSessionFactory() as session:
        org = Organisation(name="G1 Org B", slug="g1-org-b")
        user = User(
            email="g1b@example.com",
            name="G1 B",
            google_id="g1-google-b",
            organisation=org,
            role="admin",
        )
        session.add_all([org, user])
        await session.flush()
        session.add(CreditTransaction(organisation_id=org.id, user_id=user.id, amount=200, reason="seed"))
        await session.commit()
        await session.refresh(user)

    token = create_access_token(
        {"user_id": str(user.id), "organisation_id": str(user.organisation_id), "role": "admin"}
    )
    payload = {"text": "This is valid analysis input for rate limit rejection."}

    with TestClient(app) as client:
        r1 = client.post("/api/analyse", headers={"Authorization": f"Bearer {token}"}, json=payload)
        r2 = client.post("/api/analyse", headers={"Authorization": f"Bearer {token}"}, json=payload)
        r3 = client.post("/api/analyse", headers={"Authorization": f"Bearer {token}"}, json=payload)

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429
    assert "Retry-After" in r3.headers


@pytest.mark.asyncio
async def test_tenant_isolation_enforced_separate_limits():
    from app.core.security import create_access_token

    app, db, Organisation, User, CreditTransaction = await _prepare_app_and_db()
    async with db.AsyncSessionFactory() as session:
        org_a = Organisation(name="G1 Org C", slug="g1-org-c")
        org_b = Organisation(name="G1 Org D", slug="g1-org-d")
        user_a = User(
            email="g1c@example.com",
            name="G1 C",
            google_id="g1-google-c",
            organisation=org_a,
            role="member",
        )
        user_b = User(
            email="g1d@example.com",
            name="G1 D",
            google_id="g1-google-d",
            organisation=org_b,
            role="member",
        )
        session.add_all([org_a, org_b, user_a, user_b])
        await session.flush()
        session.add_all(
            [
                CreditTransaction(organisation_id=org_a.id, user_id=user_a.id, amount=200, reason="seed-a"),
                CreditTransaction(organisation_id=org_b.id, user_id=user_b.id, amount=200, reason="seed-b"),
            ]
        )
        await session.commit()
        await session.refresh(user_a)
        await session.refresh(user_b)

    token_a = create_access_token(
        {"user_id": str(user_a.id), "organisation_id": str(user_a.organisation_id), "role": "member"}
    )
    token_b = create_access_token(
        {"user_id": str(user_b.id), "organisation_id": str(user_b.organisation_id), "role": "member"}
    )
    payload = {"text": "This is valid analysis input for tenant isolation."}

    with TestClient(app) as client:
        a1 = client.post("/api/analyse", headers={"Authorization": f"Bearer {token_a}"}, json=payload)
        a2 = client.post("/api/analyse", headers={"Authorization": f"Bearer {token_a}"}, json=payload)
        a3 = client.post("/api/analyse", headers={"Authorization": f"Bearer {token_a}"}, json=payload)
        b1 = client.post("/api/analyse", headers={"Authorization": f"Bearer {token_b}"}, json=payload)

    assert a1.status_code == 200
    assert a2.status_code == 200
    assert a3.status_code == 429
    assert b1.status_code == 200
