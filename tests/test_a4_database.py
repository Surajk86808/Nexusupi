"""
Task A4 Validation: Async database engine and session factory tests.
"""

import asyncio
import sys
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def sqlite_env(monkeypatch):
    """
    Override DATABASE_URL for these tests to use in-memory SQLite.

    This avoids requiring a running PostgreSQL instance while still
    exercising the async engine and session factory.
    """
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("JWT_SECRET", "a" * 32)

    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _reload_db_module():
    """Reload app.core.database so it picks up the overridden DATABASE_URL."""
    import importlib
    import app.core.database as db

    return importlib.reload(db)


@pytest.mark.asyncio
async def test_engine_initializes_successfully(sqlite_env):
    db = _reload_db_module()
    assert db.engine is not None
    # simple connectivity check using healthcheck helper
    ok = await db.db_healthcheck()
    assert ok is True


@pytest.mark.asyncio
async def test_session_open_and_close(sqlite_env):
    db = _reload_db_module()
    async with db.AsyncSessionFactory() as session:
        assert isinstance(session, AsyncSession)
        result = await session.execute(text("SELECT 1"))
        assert result.scalar_one() == 1


@pytest.mark.asyncio
async def test_transaction_commit(sqlite_env):
    db = _reload_db_module()

    async with db.AsyncSessionFactory() as session:
        # create a simple table and insert a row inside a transaction
        await session.execute(text("CREATE TABLE IF NOT EXISTS t (id INTEGER PRIMARY KEY, value INTEGER)"))
        await session.execute(text("INSERT INTO t (value) VALUES (42)"))
        await session.commit()

        result = await session.execute(text("SELECT value FROM t"))
        values = [row[0] for row in result.all()]
        assert 42 in values


@pytest.mark.asyncio
async def test_transaction_rollback(sqlite_env):
    db = _reload_db_module()

    async with db.AsyncSessionFactory() as session:
        await session.execute(text("CREATE TABLE IF NOT EXISTS t_rb (id INTEGER PRIMARY KEY, value INTEGER)"))

    with pytest.raises(RuntimeError):
        async with db.transactional_session() as session:
            await session.execute(text("INSERT INTO t_rb (value) VALUES (99)"))
            # force an error to trigger rollback
            raise RuntimeError("force rollback")

    # Verify that the row was not committed
    async with db.AsyncSessionFactory() as session:
        result = await session.execute(text("SELECT COUNT(*) FROM t_rb"))
        count = result.scalar_one()
        assert count == 0


@pytest.mark.asyncio
async def test_multiple_sessions_concurrent(sqlite_env):
    db = _reload_db_module()

    async def ping():
        async with db.AsyncSessionFactory() as session:
            result = await session.execute(text("SELECT 1"))
            return result.scalar_one()

    results = await asyncio.gather(*[ping() for _ in range(5)])
    assert all(r == 1 for r in results)


@pytest.mark.asyncio
async def test_fastapi_dependency_injection(sqlite_env):
    """
    Ensure get_db works as a FastAPI dependency and sessions are usable.
    """
    db = _reload_db_module()

    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()

    @app.get("/db-ping")
    async def db_ping(session: AsyncSession = Depends(db.get_db)):
        result = await session.execute(text("SELECT 1"))
        return {"ok": result.scalar_one() == 1}

    client = TestClient(app)
    resp = client.get("/db-ping")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

