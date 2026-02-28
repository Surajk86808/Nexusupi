"""
Task B2 Validation: User model tests.
"""

import importlib
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import selectinload

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def sqlite_env(monkeypatch):
    """
    Override DATABASE_URL for these tests to use in-memory SQLite.
    """
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("JWT_SECRET", "a" * 32)
    monkeypatch.setenv("DEBUG", "false")

    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _prepare_schema():
    """Reload DB and create schema with SQLite FK enforcement enabled."""
    import app.core.database as db

    db = importlib.reload(db)

    @event.listens_for(db.engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):  # noqa: ANN001, ARG001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    from app.models import Base, Organisation, User  # noqa: F401

    async with db.engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys=ON"))
        await conn.run_sync(Base.metadata.create_all)

    return db, Base, Organisation, User


@pytest.mark.asyncio
async def test_user_model_imports_correctly():
    _, Base, _, User = await _prepare_schema()

    table = Base.metadata.tables.get("users")
    assert table is not None

    assert "id" in table.c
    assert "email" in table.c
    assert "name" in table.c
    assert "google_id" in table.c
    assert "organisation_id" in table.c
    assert "role" in table.c
    assert "created_at" in table.c

    assert table.c.email.unique is True
    assert table.c.google_id.unique is True
    assert table.c.organisation_id.nullable is False
    assert table.c.role.nullable is False

    index_cols = [{col.name for col in idx.columns} for idx in table.indexes]
    assert any("email" in cols for cols in index_cols)
    assert any("google_id" in cols for cols in index_cols)
    assert any("organisation_id" in cols for cols in index_cols)


@pytest.mark.asyncio
async def test_user_can_be_created_successfully():
    db, _, Organisation, User = await _prepare_schema()

    async with db.AsyncSessionFactory() as session:
        org = Organisation(name="Org A", slug="org-a")
        session.add(org)
        await session.flush()

        user = User(
            email="alice@example.com",
            name="Alice",
            google_id="google-alice",
            organisation_id=org.id,
            role="member",
        )
        session.add(user)
        await session.commit()

        result = await session.execute(select(User).where(User.email == "alice@example.com"))
        created = result.scalar_one()
        assert created.name == "Alice"
        assert created.organisation_id == org.id


@pytest.mark.asyncio
async def test_organisation_relationship_works_correctly():
    db, _, Organisation, User = await _prepare_schema()

    async with db.AsyncSessionFactory() as session:
        org = Organisation(name="Org B", slug="org-b")
        session.add(org)
        await session.flush()

        user = User(
            email="bob@example.com",
            name="Bob",
            google_id="google-bob",
            organisation=org,
            role="admin",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        assert user.organisation.id == org.id
        stmt = (
            select(Organisation)
            .options(selectinload(Organisation.users))
            .where(Organisation.id == org.id)
        )
        org_with_users = (await session.execute(stmt)).scalar_one()
        assert org_with_users is not None
        assert any(u.id == user.id for u in org_with_users.users)


@pytest.mark.asyncio
async def test_foreign_key_constraint_enforced():
    db, _, _, User = await _prepare_schema()

    async with db.AsyncSessionFactory() as session:
        orphan_user = User(
            email="orphan@example.com",
            name="Orphan",
            google_id="google-orphan",
            organisation_id=uuid4(),
            role="member",
        )
        session.add(orphan_user)

        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


@pytest.mark.asyncio
async def test_unique_email_constraint_enforced():
    db, _, Organisation, User = await _prepare_schema()

    async with db.AsyncSessionFactory() as session:
        org = Organisation(name="Org C", slug="org-c")
        session.add(org)
        await session.flush()

        first = User(
            email="same@example.com",
            name="First",
            google_id="google-shared",
            organisation_id=org.id,
            role="member",
        )
        session.add(first)
        await session.commit()

        dup_email = User(
            email="same@example.com",
            name="Second",
            google_id="google-second",
            organisation_id=org.id,
            role="member",
        )
        session.add(dup_email)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


@pytest.mark.asyncio
async def test_unique_google_id_constraint_enforced():
    db, _, Organisation, User = await _prepare_schema()

    async with db.AsyncSessionFactory() as session:
        org = Organisation(name="Org C2", slug="org-c2")
        session.add(org)
        await session.flush()

        first = User(
            email="first-google@example.com",
            name="First Google",
            google_id="google-shared",
            organisation_id=org.id,
            role="member",
        )
        session.add(first)
        await session.commit()

        dup_google = User(
            email="third@example.com",
            name="Third",
            google_id="google-shared",
            organisation_id=org.id,
            role="member",
        )
        session.add(dup_google)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


@pytest.mark.asyncio
async def test_role_validation_works_correctly():
    db, _, Organisation, User = await _prepare_schema()

    async with db.AsyncSessionFactory() as session:
        org = Organisation(name="Org D", slug="org-d")
        session.add(org)
        await session.flush()

        invalid_role = User(
            email="invalid-role@example.com",
            name="Invalid",
            google_id="google-invalid-role",
            organisation_id=org.id,
            role="owner",
        )
        session.add(invalid_role)

        with pytest.raises((StatementError, IntegrityError, ValueError)):
            await session.commit()
        await session.rollback()


@pytest.mark.asyncio
async def test_multiple_users_isolated_across_organisations():
    db, _, Organisation, User = await _prepare_schema()

    async with db.AsyncSessionFactory() as session:
        org_a = Organisation(name="Org E", slug="org-e")
        org_b = Organisation(name="Org F", slug="org-f")
        session.add_all([org_a, org_b])
        await session.flush()

        user_a = User(
            email="usera@example.com",
            name="User A",
            google_id="google-user-a",
            organisation_id=org_a.id,
            role="member",
        )
        user_b = User(
            email="userb@example.com",
            name="User B",
            google_id="google-user-b",
            organisation_id=org_b.id,
            role="admin",
        )
        session.add_all([user_a, user_b])
        await session.commit()

        result_a = await session.execute(select(User).where(User.organisation_id == org_a.id))
        result_b = await session.execute(select(User).where(User.organisation_id == org_b.id))

        users_a = result_a.scalars().all()
        users_b = result_b.scalars().all()

        assert len(users_a) == 1
        assert len(users_b) == 1
        assert users_a[0].email == "usera@example.com"
        assert users_b[0].email == "userb@example.com"


@pytest.mark.asyncio
async def test_relationship_navigation_works_both_directions():
    db, _, Organisation, User = await _prepare_schema()

    async with db.AsyncSessionFactory() as session:
        org = Organisation(name="Org G", slug="org-g")
        user = User(
            email="nav@example.com",
            name="Navigator",
            google_id="google-nav",
            organisation=org,
            role="member",
        )
        session.add_all([org, user])
        await session.commit()
        await session.refresh(org)
        await session.refresh(user)

        assert user.organisation.id == org.id
        stmt = (
            select(Organisation)
            .options(selectinload(Organisation.users))
            .where(Organisation.id == org.id)
        )
        org_with_users = (await session.execute(stmt)).scalar_one()
        assert org_with_users is not None
        assert len(org_with_users.users) == 1
        assert org_with_users.users[0].email == "nav@example.com"
