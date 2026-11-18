"""Pytest fixtures providing isolated async SQLite DB and ASGI test client."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ["FLOWPILOT_ENV"] = "test"
os.environ["FLOWPILOT_LLM_PROVIDER"] = "mock"

from flowpilot.config import get_settings
from flowpilot.db.models import Base
from flowpilot.db.seed import seed_defaults
from flowpilot.db.session import get_session, reset_db_engine
from flowpilot.guardrails.budget import get_daily_spend_ledger
from flowpilot.guardrails.cache import get_tier0_cache
from flowpilot.guardrails.cancellation import get_cancellation_registry
from flowpilot.guardrails.circuit_breaker import get_circuit_breaker_registry
from flowpilot.main import create_app


@pytest.fixture(autouse=True)
def reset_singletons() -> None:
    get_settings.cache_clear()
    get_daily_spend_ledger().reset()
    get_tier0_cache().clear()
    get_circuit_breaker_registry().clear()
    get_cancellation_registry()._cancelled.clear()
    reset_db_engine()


@pytest_asyncio.fixture
async def db_session(tmp_path) -> AsyncGenerator[AsyncSession, None]:
    db_file = tmp_path / "test_flowpilot.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        await seed_defaults(session)
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession, tmp_path) -> AsyncGenerator[AsyncClient, None]:
    os.environ["FLOWPILOT_STORAGE_DIR"] = str(tmp_path / "uploads")
    get_settings.cache_clear()
    app = create_app()

    async def _override_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_session] = _override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
