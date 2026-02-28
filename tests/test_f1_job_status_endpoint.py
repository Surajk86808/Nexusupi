"""
Task F1 Validation: /api/jobs/{job_id} status endpoint tests.
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
    """Configure isolated SQLite DB for job status endpoint tests."""
    db_path = tmp_path / "test_f1_job_status.db"
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
async def test_job_status_retrieval_works():
    from app.core.security import create_access_token

    app, db, Organisation, User, CreditTransaction = await _prepare_app_and_db()

    async with db.AsyncSessionFactory() as session:
        org = Organisation(name="F1 Org A", slug="f1-org-a")
        user = User(
            email="f1a@example.com",
            name="F1 A",
            google_id="f1-google-a",
            organisation=org,
            role="admin",
        )
        session.add_all([org, user])
        await session.flush()
        session.add(CreditTransaction(organisation_id=org.id, user_id=user.id, amount=100, reason="seed"))
        await session.commit()
        await session.refresh(user)

    token = create_access_token(
        {"user_id": str(user.id), "organisation_id": str(user.organisation_id), "role": "admin"}
    )

    with TestClient(app) as client:
        create_resp = client.post(
            "/api/summarise",
            headers={"Authorization": f"Bearer {token}"},
            json={"text": "Create a summarise job so status can be fetched."},
        )
        assert create_resp.status_code == 200
        job_id = create_resp.json()["job_id"]

        status_resp = client.get(f"/api/jobs/{job_id}", headers={"Authorization": f"Bearer {token}"})

    assert status_resp.status_code == 200
    body = status_resp.json()
    assert body["job_id"] == job_id
    assert body["status"] == "pending"
    assert "result" in body
    assert "error" in body


@pytest.mark.asyncio
async def test_tenant_isolation_enforced():
    from app.core.security import create_access_token

    app, db, Organisation, User, CreditTransaction = await _prepare_app_and_db()

    async with db.AsyncSessionFactory() as session:
        org_a = Organisation(name="F1 Org B", slug="f1-org-b")
        org_b = Organisation(name="F1 Org C", slug="f1-org-c")
        user_a = User(
            email="f1b@example.com",
            name="F1 B",
            google_id="f1-google-b",
            organisation=org_a,
            role="member",
        )
        user_b = User(
            email="f1c@example.com",
            name="F1 C",
            google_id="f1-google-c",
            organisation=org_b,
            role="admin",
        )
        session.add_all([org_a, org_b, user_a, user_b])
        await session.flush()
        session.add_all(
            [
                CreditTransaction(organisation_id=org_a.id, user_id=user_a.id, amount=100, reason="seed-a"),
                CreditTransaction(organisation_id=org_b.id, user_id=user_b.id, amount=100, reason="seed-b"),
            ]
        )
        await session.commit()
        await session.refresh(user_a)
        await session.refresh(user_b)

    token_a = create_access_token(
        {"user_id": str(user_a.id), "organisation_id": str(user_a.organisation_id), "role": "member"}
    )
    token_b = create_access_token(
        {"user_id": str(user_b.id), "organisation_id": str(user_b.organisation_id), "role": "admin"}
    )

    with TestClient(app) as client:
        create_resp = client.post(
            "/api/summarise",
            headers={"Authorization": f"Bearer {token_a}"},
            json={"text": "Tenant A job should not be visible by tenant B."},
        )
        assert create_resp.status_code == 200
        job_id = create_resp.json()["job_id"]

        read_resp = client.get(f"/api/jobs/{job_id}", headers={"Authorization": f"Bearer {token_b}"})

    assert read_resp.status_code == 403


@pytest.mark.asyncio
async def test_invalid_job_id_rejected():
    from app.core.security import create_access_token

    app, db, Organisation, User, CreditTransaction = await _prepare_app_and_db()

    async with db.AsyncSessionFactory() as session:
        org = Organisation(name="F1 Org D", slug="f1-org-d")
        user = User(
            email="f1d@example.com",
            name="F1 D",
            google_id="f1-google-d",
            organisation=org,
            role="admin",
        )
        session.add_all([org, user])
        await session.flush()
        session.add(CreditTransaction(organisation_id=org.id, user_id=user.id, amount=100, reason="seed"))
        await session.commit()
        await session.refresh(user)

    token = create_access_token(
        {"user_id": str(user.id), "organisation_id": str(user.organisation_id), "role": "admin"}
    )
    with TestClient(app) as client:
        response = client.get("/api/jobs/not-a-uuid", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 422
