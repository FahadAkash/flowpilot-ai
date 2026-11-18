"""Lazy singleton async SQLAlchemy engine and session helpers."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from flowpilot.config import get_settings
from flowpilot.db.models import Base

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine(database_url: str | None = None) -> AsyncEngine:
    """Return or initialize the lazy singleton AsyncEngine."""
    global _engine, _session_factory
    if _engine is None or database_url is not None:
        settings = get_settings()
        url = database_url or settings.database_url
        kwargs: dict[str, object] = {"pool_pre_ping": True}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
        engine = create_async_engine(url, **kwargs)
        if database_url is None:
            _engine = engine
            _session_factory = async_sessionmaker(
                _engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
        return engine
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the async session maker."""
    global _session_factory
    if _session_factory is None:
        engine = get_engine()
        _session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


def reset_db_engine() -> None:
    """Reset module-level singletons (used by tests)."""
    global _engine, _session_factory
    _engine = None
    _session_factory = None


async def init_db(engine: AsyncEngine | None = None) -> None:
    """Create pgvector extension (when on PostgreSQL) and all tables."""
    target = engine or get_engine()
    async with target.begin() as conn:
        if conn.dialect.name == "postgresql":
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI async session dependency."""
    factory = get_session_factory()
    async with factory() as session:
        yield session
