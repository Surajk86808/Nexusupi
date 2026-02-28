"""
Task D3 Validation: atomic credit deduction service tests.
"""

import asyncio
import importlib
import sys
from pathlib import Path

import pytest
from sqlalchemy import event, func, select, text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def sqlite_env(monkeypatch, tmp_path):
    """Configure isolated SQLite DB for credit service tests."""
    db_path = tmp_path / "test_d3_deduct_credits.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("JWT_SECRET", "a" * 32)
    monkeypatch.setenv("DEBUG", "false")

    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _prepare_schema():
    """Reload DB and create schema with FK enforcement."""
    import app.core.database as db

    db = importlib.reload(db)

    @event.listens_for(db.engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):  # noqa: ANN001, ARG001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    from app.models import Base, CreditTransaction, Organisation, User  # noqa: F401

    async with db.engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys=ON"))
        await conn.run_sync(Base.metadata.create_all)

    return db, Organisation, User, CreditTransaction


@pytest.mark.asyncio
async def test_successful_deduction():
    from app.services.credit_service import deduct_credits

    db, Organisation, User, CreditTransaction = await _prepare_schema()
    async with db.AsyncSessionFactory() as session:
        org = Organisation(name="D3 Org A", slug="d3-org-a")
        user = User(
            email="d3a@example.com",
            name="D3 A",
            google_id="d3-google-a",
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

        txn = await deduct_credits(
            session,
            organisation_id=org.id,
            user_id=user.id,
            amount=30,
            reason="usage",
        )
        await session.refresh(txn)
        assert txn.amount == -30

    async with db.AsyncSessionFactory() as session:
        balance = (
            await session.execute(
                select(func.coalesce(func.sum(CreditTransaction.amount), 0)).where(
                    CreditTransaction.organisation_id == org.id
                )
            )
        ).scalar_one()
        assert balance == 70


@pytest.mark.asyncio
async def test_insufficient_balance_rejection():
    from app.services.credit_service import InsufficientCreditsError, deduct_credits

    db, Organisation, User, CreditTransaction = await _prepare_schema()
    async with db.AsyncSessionFactory() as session:
        org = Organisation(name="D3 Org B", slug="d3-org-b")
        user = User(
            email="d3b@example.com",
            name="D3 B",
            google_id="d3-google-b",
            organisation=org,
            role="member",
        )
        session.add_all([org, user])
        await session.flush()
        session.add(
            CreditTransaction(organisation_id=org.id, user_id=user.id, amount=20, reason="seed")
        )
        await session.commit()

        with pytest.raises(InsufficientCreditsError):
            await deduct_credits(
                session,
                organisation_id=org.id,
                user_id=user.id,
                amount=50,
                reason="too-much",
            )

    async with db.AsyncSessionFactory() as session:
        count = (
            await session.execute(select(func.count(CreditTransaction.id)))
        ).scalar_one()
        assert count == 1


@pytest.mark.asyncio
async def test_concurrent_deduction_safety():
    from app.services.credit_service import InsufficientCreditsError, deduct_credits

    db, Organisation, User, CreditTransaction = await _prepare_schema()
    async with db.AsyncSessionFactory() as session:
        org = Organisation(name="D3 Org C", slug="d3-org-c")
        user = User(
            email="d3c@example.com",
            name="D3 C",
            google_id="d3-google-c",
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

    start = asyncio.Event()

    async def run_deduction(idx: int):
        async with db.AsyncSessionFactory() as session:
            await start.wait()
            try:
                await deduct_credits(
                    session,
                    organisation_id=org.id,
                    user_id=user.id,
                    amount=80,
                    reason=f"concurrent-{idx}",
                    idempotency_key=f"d3-concurrent-{idx}",
                )
                return "ok"
            except InsufficientCreditsError:
                return "insufficient"

    tasks = [asyncio.create_task(run_deduction(1)), asyncio.create_task(run_deduction(2))]
    start.set()
    results = await asyncio.gather(*tasks)

    assert sorted(results) == ["insufficient", "ok"]

    async with db.AsyncSessionFactory() as session:
        balance = (
            await session.execute(
                select(func.coalesce(func.sum(CreditTransaction.amount), 0)).where(
                    CreditTransaction.organisation_id == org.id
                )
            )
        ).scalar_one()
        assert balance == 20


@pytest.mark.asyncio
async def test_idempotency_enforcement():
    from app.services.credit_service import deduct_credits

    db, Organisation, User, CreditTransaction = await _prepare_schema()
    async with db.AsyncSessionFactory() as session:
        org = Organisation(name="D3 Org D", slug="d3-org-d")
        user = User(
            email="d3d@example.com",
            name="D3 D",
            google_id="d3-google-d",
            organisation=org,
            role="admin",
        )
        session.add_all([org, user])
        await session.flush()
        session.add(
            CreditTransaction(organisation_id=org.id, user_id=user.id, amount=100, reason="seed")
        )
        await session.commit()

        first = await deduct_credits(
            session,
            organisation_id=org.id,
            user_id=user.id,
            amount=10,
            reason="first",
            idempotency_key="dup-key",
        )

        second = await deduct_credits(
            session,
            organisation_id=org.id,
            user_id=user.id,
            amount=10,
            reason="second",
            idempotency_key="dup-key",
        )
        assert second.id == first.id

    async with db.AsyncSessionFactory() as session:
        deductions = (
            await session.execute(
                select(func.count(CreditTransaction.id)).where(CreditTransaction.idempotency_key == "dup-key")
            )
        ).scalar_one()
        assert deductions == 1
        balance = (
            await session.execute(
                select(func.coalesce(func.sum(CreditTransaction.amount), 0)).where(
                    CreditTransaction.organisation_id == org.id
                )
            )
        ).scalar_one()
        assert balance == 90


@pytest.mark.asyncio
async def test_atomic_transaction_rollback():
    from app.services.credit_service import deduct_credits

    db, Organisation, User, CreditTransaction = await _prepare_schema()
    async with db.AsyncSessionFactory() as session:
        org = Organisation(name="D3 Org E", slug="d3-org-e")
        user = User(
            email="d3e@example.com",
            name="D3 E",
            google_id="d3-google-e",
            organisation=org,
            role="admin",
        )
        session.add_all([org, user])
        await session.flush()
        session.add(
            CreditTransaction(organisation_id=org.id, user_id=user.id, amount=100, reason="seed")
        )
        await session.commit()
        org_id = org.id
        user_id = user.id

        original_flush = session.flush

        async def broken_flush(*args, **kwargs):  # noqa: ANN002, ANN003
            raise RuntimeError("forced failure")

        session.flush = broken_flush  # type: ignore[method-assign]
        with pytest.raises(RuntimeError):
            await deduct_credits(
                session,
                organisation_id=org_id,
                user_id=user_id,
                amount=25,
                reason="will-rollback",
            )
        session.flush = original_flush  # type: ignore[method-assign]

    async with db.AsyncSessionFactory() as session:
        balance = (
            await session.execute(
                select(func.coalesce(func.sum(CreditTransaction.amount), 0)).where(
                    CreditTransaction.organisation_id == org_id
                )
            )
        ).scalar_one()
        assert balance == 100
