"""
Task B3 Validation: CreditTransaction model tests.
"""

import importlib
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import UniqueConstraint
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import IntegrityError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def sqlite_env(monkeypatch):
    """Override test env vars for SQLite-based async tests."""
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("JWT_SECRET", "a" * 32)
    monkeypatch.setenv("DEBUG", "false")

    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _prepare_schema():
    """Reload DB module and create a fresh schema with FK enforcement."""
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

    return db, Base, Organisation, User, CreditTransaction


@pytest.mark.asyncio
async def test_credit_transaction_model_imports_correctly():
    _, Base, _, _, _ = await _prepare_schema()

    table = Base.metadata.tables.get("credit_transactions")
    assert table is not None

    assert "id" in table.c
    assert "organisation_id" in table.c
    assert "user_id" in table.c
    assert "amount" in table.c
    assert "reason" in table.c
    assert "idempotency_key" in table.c
    assert "created_at" in table.c
    assert "balance" not in table.c

    assert table.c.idempotency_key.unique is not True
    index_cols = [{col.name for col in idx.columns} for idx in table.indexes]
    assert any("organisation_id" in cols for cols in index_cols)
    assert any("user_id" in cols for cols in index_cols)
    assert any("idempotency_key" in cols for cols in index_cols)
    unique_constraints = [
        {col.name for col in cons.columns}
        for cons in table.constraints
        if isinstance(cons, UniqueConstraint)
    ]
    assert any({"organisation_id", "idempotency_key"} == cols for cols in unique_constraints)


@pytest.mark.asyncio
async def test_transaction_creation_works():
    db, _, Organisation, User, CreditTransaction = await _prepare_schema()

    async with db.AsyncSessionFactory() as session:
        org = Organisation(name="Org A", slug="b3-org-a")
        user = User(
            email="b3-a@example.com",
            name="User A",
            google_id="b3-google-a",
            organisation=org,
            role="member",
        )
        session.add_all([org, user])
        await session.flush()

        txn = CreditTransaction(
            organisation_id=org.id,
            user_id=user.id,
            amount=100,
            reason="initial_credit",
            idempotency_key="b3-create-1",
        )
        session.add(txn)
        await session.commit()

        result = await session.execute(
            select(CreditTransaction).where(CreditTransaction.idempotency_key == "b3-create-1")
        )
        created = result.scalar_one()
        assert created.amount == 100
        assert created.reason == "initial_credit"


@pytest.mark.asyncio
async def test_positive_and_negative_amounts_allowed():
    db, _, Organisation, User, CreditTransaction = await _prepare_schema()

    async with db.AsyncSessionFactory() as session:
        org = Organisation(name="Org B", slug="b3-org-b")
        user = User(
            email="b3-b@example.com",
            name="User B",
            google_id="b3-google-b",
            organisation=org,
            role="admin",
        )
        session.add_all([org, user])
        await session.flush()

        session.add_all(
            [
                CreditTransaction(
                    organisation_id=org.id,
                    user_id=user.id,
                    amount=250,
                    reason="credit_add",
                    idempotency_key="b3-amt-1",
                ),
                CreditTransaction(
                    organisation_id=org.id,
                    user_id=user.id,
                    amount=-40,
                    reason="credit_deduct",
                    idempotency_key="b3-amt-2",
                ),
            ]
        )
        await session.commit()

        rows = (
            await session.execute(
                select(CreditTransaction.amount).where(CreditTransaction.organisation_id == org.id)
            )
        ).scalars().all()
        assert 250 in rows
        assert -40 in rows


@pytest.mark.asyncio
async def test_fk_enforcement_works():
    db, _, Organisation, User, CreditTransaction = await _prepare_schema()

    async with db.AsyncSessionFactory() as session:
        org = Organisation(name="Org C", slug="b3-org-c")
        user = User(
            email="b3-c@example.com",
            name="User C",
            google_id="b3-google-c",
            organisation=org,
            role="member",
        )
        session.add_all([org, user])
        await session.flush()

        bad_org_txn = CreditTransaction(
            organisation_id=uuid4(),
            user_id=user.id,
            amount=10,
            reason="bad_org",
            idempotency_key="b3-fk-1",
        )
        session.add(bad_org_txn)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

        bad_user_txn = CreditTransaction(
            organisation_id=org.id,
            user_id=uuid4(),
            amount=10,
            reason="bad_user",
            idempotency_key="b3-fk-2",
        )
        session.add(bad_user_txn)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


@pytest.mark.asyncio
async def test_idempotency_key_uniqueness_enforced():
    db, _, Organisation, User, CreditTransaction = await _prepare_schema()

    async with db.AsyncSessionFactory() as session:
        org = Organisation(name="Org D", slug="b3-org-d")
        user = User(
            email="b3-d@example.com",
            name="User D",
            google_id="b3-google-d",
            organisation=org,
            role="member",
        )
        session.add_all([org, user])
        await session.flush()

        first = CreditTransaction(
            organisation_id=org.id,
            user_id=user.id,
            amount=50,
            reason="first",
            idempotency_key="b3-idem-1",
        )
        session.add(first)
        await session.commit()

        dup = CreditTransaction(
            organisation_id=org.id,
            user_id=user.id,
            amount=50,
            reason="duplicate",
            idempotency_key="b3-idem-1",
        )
        session.add(dup)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


@pytest.mark.asyncio
async def test_idempotency_key_can_repeat_across_organisations():
    db, _, Organisation, User, CreditTransaction = await _prepare_schema()

    async with db.AsyncSessionFactory() as session:
        org_a = Organisation(name="Org I", slug="b3-org-i")
        org_b = Organisation(name="Org J", slug="b3-org-j")
        user_a = User(
            email="b3-i@example.com",
            name="User I",
            google_id="b3-google-i",
            organisation=org_a,
            role="member",
        )
        user_b = User(
            email="b3-j@example.com",
            name="User J",
            google_id="b3-google-j",
            organisation=org_b,
            role="member",
        )
        session.add_all([org_a, org_b, user_a, user_b])
        await session.flush()

        session.add_all(
            [
                CreditTransaction(
                    organisation_id=org_a.id,
                    user_id=user_a.id,
                    amount=25,
                    reason="org_a_txn",
                    idempotency_key="shared-key",
                ),
                CreditTransaction(
                    organisation_id=org_b.id,
                    user_id=user_b.id,
                    amount=30,
                    reason="org_b_txn",
                    idempotency_key="shared-key",
                ),
            ]
        )
        await session.commit()


@pytest.mark.asyncio
async def test_ledger_supports_multiple_transactions_safely():
    db, _, Organisation, User, CreditTransaction = await _prepare_schema()

    async with db.AsyncSessionFactory() as session:
        org = Organisation(name="Org E", slug="b3-org-e")
        user = User(
            email="b3-e@example.com",
            name="User E",
            google_id="b3-google-e",
            organisation=org,
            role="member",
        )
        session.add_all([org, user])
        await session.flush()

        session.add_all(
            [
                CreditTransaction(
                    organisation_id=org.id,
                    user_id=user.id,
                    amount=100,
                    reason="add_1",
                    idempotency_key="b3-ledger-1",
                ),
                CreditTransaction(
                    organisation_id=org.id,
                    user_id=user.id,
                    amount=-20,
                    reason="deduct_1",
                    idempotency_key="b3-ledger-2",
                ),
                CreditTransaction(
                    organisation_id=org.id,
                    user_id=user.id,
                    amount=30,
                    reason="add_2",
                    idempotency_key="b3-ledger-3",
                ),
            ]
        )
        await session.commit()

        count = (
            await session.execute(
                select(func.count(CreditTransaction.id)).where(
                    CreditTransaction.organisation_id == org.id
                )
            )
        ).scalar_one()
        assert count == 3


@pytest.mark.asyncio
async def test_credit_balance_derivable_using_sum_amount():
    db, _, Organisation, User, CreditTransaction = await _prepare_schema()

    async with db.AsyncSessionFactory() as session:
        org = Organisation(name="Org F", slug="b3-org-f")
        user = User(
            email="b3-f@example.com",
            name="User F",
            google_id="b3-google-f",
            organisation=org,
            role="member",
        )
        session.add_all([org, user])
        await session.flush()

        session.add_all(
            [
                CreditTransaction(
                    organisation_id=org.id,
                    user_id=user.id,
                    amount=200,
                    reason="top_up",
                    idempotency_key="b3-sum-1",
                ),
                CreditTransaction(
                    organisation_id=org.id,
                    user_id=user.id,
                    amount=-75,
                    reason="usage",
                    idempotency_key="b3-sum-2",
                ),
                CreditTransaction(
                    organisation_id=org.id,
                    user_id=user.id,
                    amount=-25,
                    reason="usage",
                    idempotency_key="b3-sum-3",
                ),
            ]
        )
        await session.commit()

        derived_balance = (
            await session.execute(
                select(func.sum(CreditTransaction.amount)).where(
                    CreditTransaction.organisation_id == org.id,
                    CreditTransaction.user_id == user.id,
                )
            )
        ).scalar_one()
        assert derived_balance == 100


@pytest.mark.asyncio
async def test_organisation_isolation_enforced():
    db, _, Organisation, User, CreditTransaction = await _prepare_schema()

    async with db.AsyncSessionFactory() as session:
        org_a = Organisation(name="Org G", slug="b3-org-g")
        org_b = Organisation(name="Org H", slug="b3-org-h")
        user_a = User(
            email="b3-g@example.com",
            name="User G",
            google_id="b3-google-g",
            organisation=org_a,
            role="member",
        )
        user_b = User(
            email="b3-h@example.com",
            name="User H",
            google_id="b3-google-h",
            organisation=org_b,
            role="admin",
        )
        session.add_all([org_a, org_b, user_a, user_b])
        await session.flush()

        session.add_all(
            [
                CreditTransaction(
                    organisation_id=org_a.id,
                    user_id=user_a.id,
                    amount=120,
                    reason="org_a_credit",
                    idempotency_key="b3-iso-1",
                ),
                CreditTransaction(
                    organisation_id=org_b.id,
                    user_id=user_b.id,
                    amount=300,
                    reason="org_b_credit",
                    idempotency_key="b3-iso-2",
                ),
            ]
        )
        await session.commit()

        total_a = (
            await session.execute(
                select(func.sum(CreditTransaction.amount)).where(
                    CreditTransaction.organisation_id == org_a.id
                )
            )
        ).scalar_one()
        total_b = (
            await session.execute(
                select(func.sum(CreditTransaction.amount)).where(
                    CreditTransaction.organisation_id == org_b.id
                )
            )
        ).scalar_one()

        assert total_a == 120
        assert total_b == 300
