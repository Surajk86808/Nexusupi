"""
Async database engine and session management.

Uses SQLAlchemy 2.0 async engine with connection pooling configured
for production, and an async session factory suitable for FastAPI.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.engine import make_url
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings


settings = get_settings()

# Handle Neon SSL - asyncpg needs ssl in connect_args not URL param
_connect_args = {}
_db_url = settings.database_url

if "ssl=require" in _db_url:
    _db_url = _db_url.replace("?ssl=require", "").replace("&ssl=require", "")
    _connect_args["ssl"] = "require"

# Determine whether we're using SQLite; some pool options are not supported.
_url = make_url(_db_url)
_is_sqlite = _url.get_backend_name() == "sqlite"

_engine_kwargs: dict = {
    "echo": settings.debug,
    "pool_pre_ping": True,
    "pool_recycle": 1800,
    "connect_args": _connect_args,
}

if not _is_sqlite:
    _engine_kwargs.update(
        {
            "pool_size": 5,
            "max_overflow": 10,
        }
    )

engine: AsyncEngine = create_async_engine(_db_url, **_engine_kwargs)

# Async session factory
AsyncSessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that provides an AsyncSession.

    Ensures the session is closed after request handling, and is safe
    for concurrent usage (one session per request).
    """
    async with AsyncSessionFactory() as session:
        try:
            yield session
        finally:
            await session.close()


@asynccontextmanager
async def transactional_session() -> AsyncIterator[AsyncSession]:
    """
    Provide an AsyncSession wrapped in a database transaction.

    The transaction is committed on success and rolled back on error,
    ensuring atomic execution of the enclosed operations.
    """
    async with AsyncSessionFactory() as session:
        try:
            async with session.begin():
                yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def db_healthcheck() -> bool:
    """
    Lightweight connectivity check: execute `SELECT 1`.

    Returns True if the database responds, otherwise propagates the error.
    """
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        scalar = result.scalar_one_or_none()
        return scalar == 1

