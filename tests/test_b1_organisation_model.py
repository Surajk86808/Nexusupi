"""
Task B1 Validation: Organisation model tests.
"""

import sys
from pathlib import Path

import pytest
from sqlalchemy import Index, String, text, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def sqlite_env(monkeypatch):
    """
    Override DATABASE_URL for these tests to use file-based SQLite.

    File-based DB ensures schema and data are visible across connections.
    """
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("JWT_SECRET", "a" * 32)

    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _prepare_schema():
    """Reload DB module, import Organisation, and create a fresh schema."""
    import importlib
    import app.core.database as db

    db = importlib.reload(db)
    from app.models.organisation import Organisation  # noqa: F401
    from app.models.base import Base

    # Create schema for this in-memory database
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    return db, Base, Organisation


@pytest.mark.asyncio
async def test_organisation_model_imports_and_metadata():
    db, Base, Organisation = await _prepare_schema()

    table = Base.metadata.tables.get("organisations")
    assert table is not None

    # Columns
    assert "id" in table.c
    assert "name" in table.c
    assert "slug" in table.c
    assert "created_at" in table.c

    # Uniqueness on slug
    assert table.c.slug.unique is True

    # Indexes on name and slug
    index_columns = {idx.name: {col.name for col in idx.columns} for idx in table.indexes}
    assert any("name" in cols for cols in index_columns.values())
    assert any("slug" in cols for cols in index_columns.values())


@pytest.mark.asyncio
async def test_slug_uniqueness_enforced():
    db, Base, Organisation = await _prepare_schema()

    async with db.AsyncSessionFactory() as session:
        org1 = Organisation(name="Org One", slug="org-one")
        session.add(org1)
        await session.commit()

        org2 = Organisation(name="Org Two", slug="org-one")
        session.add(org2)

        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


@pytest.mark.asyncio
async def test_create_and_query_organisation():
    db, Base, Organisation = await _prepare_schema()

    async with db.AsyncSessionFactory() as session:
        org1 = Organisation(name="Alpha Corp", slug="alpha")
        org2 = Organisation(name="Beta Corp", slug="beta")
        session.add_all([org1, org2])
        await session.commit()

        stmt = select(Organisation).where(Organisation.slug == "beta")
        result = await session.execute(stmt)
        org = result.scalar_one()
        assert org.name == "Beta Corp"
        assert org.slug == "beta"


@pytest.mark.asyncio
async def test_multiple_organisations_isolated():
    db, Base, Organisation = await _prepare_schema()

    async with db.AsyncSessionFactory() as session:
        a = Organisation(name="Tenant A", slug="tenant-a")
        b = Organisation(name="Tenant B", slug="tenant-b")
        session.add_all([a, b])
        await session.commit()

        stmt_a = select(Organisation).where(Organisation.slug == "tenant-a")
        stmt_b = select(Organisation).where(Organisation.slug == "tenant-b")

        res_a = await session.execute(stmt_a)
        res_b = await session.execute(stmt_b)

        org_a = res_a.scalar_one()
        org_b = res_b.scalar_one()

        assert org_a.id != org_b.id
        assert org_a.slug == "tenant-a"
        assert org_b.slug == "tenant-b"
