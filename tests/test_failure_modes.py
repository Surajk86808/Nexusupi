"""
Failure-mode coverage tests for NexusAPI.
"""

from __future__ import annotations

import asyncio
import importlib
import sys
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def sqlite_env(monkeypatch, tmp_path):
    """Configure isolated SQLite DB and settings for failure-mode tests."""
    db_path = tmp_path / "test_failure_modes.db"
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
    from app.models import Base, CreditTransaction, Job, Organisation, User

    async with db.engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys=ON"))
        await conn.run_sync(Base.metadata.create_all)

    app = create_app()

    async def override_get_db():
        async with db.AsyncSessionFactory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    return app, db, Organisation, User, CreditTransaction, Job


async def _seed_user_and_token(db, Organisation, User, CreditTransaction, amount: int, slug: str, role: str = "member"):
    from app.core.security import create_access_token

    async with db.AsyncSessionFactory() as session:
        org = Organisation(name=f"{slug}-org", slug=slug)
        user = User(
            email=f"{slug}@example.com",
            name=slug,
            google_id=f"{slug}-google",
            organisation=org,
            role=role,
        )
        session.add_all([org, user])
        await session.flush()
        if amount != 0:
            session.add(CreditTransaction(organisation_id=org.id, user_id=user.id, amount=amount, reason="seed"))
        await session.commit()
        await session.refresh(user)

    token = create_access_token(
        {"user_id": str(user.id), "organisation_id": str(user.organisation_id), "role": role}
    )
    return org, user, token


def test_health_returns_503_when_db_unreachable(monkeypatch):
    from app.main import create_app
    import app.api.routes.health as health_module

    async def _raise():
        raise RuntimeError("db down")

    monkeypatch.setattr(health_module, "db_healthcheck", _raise)
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_analyse_with_zero_credits_returns_402():
    app, db, Organisation, User, CreditTransaction, _ = await _prepare_app_and_db()
    _, _, token = await _seed_user_and_token(db, Organisation, User, CreditTransaction, 0, "fm-zero")

    with TestClient(app) as client:
        response = client.post(
            "/api/analyse",
            headers={"Authorization": f"Bearer {token}"},
            json={"text": "This text is long enough for analysis call."},
        )

    assert response.status_code == 402
    body = response.json()
    assert body["error"] == "insufficient_credits"
    assert body["balance"] == 0
    assert body["required"] == 25


@pytest.mark.asyncio
async def test_analyse_with_24_credits_returns_402():
    app, db, Organisation, User, CreditTransaction, _ = await _prepare_app_and_db()
    _, _, token = await _seed_user_and_token(db, Organisation, User, CreditTransaction, 24, "fm-twentyfour")

    with TestClient(app) as client:
        response = client.post(
            "/api/analyse",
            headers={"Authorization": f"Bearer {token}"},
            json={"text": "This text is long enough for analysis call."},
        )

    assert response.status_code == 402


@pytest.mark.asyncio
async def test_simultaneous_25_credit_deductions_only_one_succeeds():
    app, db, Organisation, User, CreditTransaction, _ = await _prepare_app_and_db()
    _, _, token = await _seed_user_and_token(db, Organisation, User, CreditTransaction, 25, "fm-concurrent")

    transport = httpx.ASGITransport(app=app)

    async def _request_once():
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post(
                "/api/analyse",
                headers={"Authorization": f"Bearer {token}"},
                json={"text": "Concurrent requests should permit only one success path."},
            )

    r1, r2 = await asyncio.gather(_request_once(), _request_once())
    statuses = sorted([r1.status_code, r2.status_code])
    assert statuses == [200, 402]


@pytest.mark.asyncio
async def test_job_not_found_returns_404():
    app, db, Organisation, User, CreditTransaction, _ = await _prepare_app_and_db()
    _, _, token = await _seed_user_and_token(db, Organisation, User, CreditTransaction, 100, "fm-job-missing")

    with TestClient(app) as client:
        response = client.get(
            f"/api/jobs/{uuid4()}",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_job_from_other_org_returns_404():
    app, db, Organisation, User, CreditTransaction, _ = await _prepare_app_and_db()
    _, _, token_a = await _seed_user_and_token(db, Organisation, User, CreditTransaction, 100, "fm-job-a")
    _, _, token_b = await _seed_user_and_token(db, Organisation, User, CreditTransaction, 100, "fm-job-b")

    with TestClient(app) as client:
        create_resp = client.post(
            "/api/summarise",
            headers={"Authorization": f"Bearer {token_a}"},
            json={"text": "Create a job for org a and fetch with org b token."},
        )
        assert create_resp.status_code == 200
        job_id = create_resp.json()["job_id"]

        read_resp = client.get(
            f"/api/jobs/{job_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )

    assert read_resp.status_code == 404


@pytest.mark.asyncio
async def test_text_too_short_returns_422():
    app, db, Organisation, User, CreditTransaction, _ = await _prepare_app_and_db()
    _, _, token = await _seed_user_and_token(db, Organisation, User, CreditTransaction, 100, "fm-short")

    with TestClient(app) as client:
        response = client.post(
            "/api/analyse",
            headers={"Authorization": f"Bearer {token}"},
            json={"text": "short"},
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_text_too_long_returns_422():
    app, db, Organisation, User, CreditTransaction, _ = await _prepare_app_and_db()
    _, _, token = await _seed_user_and_token(db, Organisation, User, CreditTransaction, 100, "fm-long")

    with TestClient(app) as client:
        response = client.post(
            "/api/analyse",
            headers={"Authorization": f"Bearer {token}"},
            json={"text": "x" * 2001},
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_missing_text_field_returns_422():
    app, db, Organisation, User, CreditTransaction, _ = await _prepare_app_and_db()
    _, _, token = await _seed_user_and_token(db, Organisation, User, CreditTransaction, 100, "fm-missing")

    with TestClient(app) as client:
        response = client.post(
            "/api/analyse",
            headers={"Authorization": f"Bearer {token}"},
            json={},
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_redis_down_fails_open_by_default(monkeypatch):
    app, db, Organisation, User, CreditTransaction, _ = await _prepare_app_and_db()
    _, _, token = await _seed_user_and_token(db, Organisation, User, CreditTransaction, 100, "fm-redis")

    async def _raise():
        raise RuntimeError("redis down")

    monkeypatch.setattr("app.middleware.rate_limit.get_redis_client", _raise)
    payload = {"text": "This is valid analysis input while Redis is unavailable."}

    with TestClient(app) as client:
        response = client.post(
            "/api/analyse",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
    assert response.status_code == 200
