import os

# Must be set before any app module is imported so pydantic-settings picks them up.
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "0:test")
os.environ.setdefault("TELEGRAM_ADMIN_ID", "999")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import message_scheduler.api as api_mod
import message_scheduler.users as users_mod
from message_scheduler.database import Base


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def sf(db_engine):
    """SQLite-backed async session factory for a single test."""
    return async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture
async def patch_users_db(sf, monkeypatch):
    """Redirect users module to the in-memory SQLite session factory."""
    monkeypatch.setattr(users_mod, "async_session_factory", sf)


@pytest_asyncio.fixture
async def patch_full_db(sf, monkeypatch):
    """Redirect both the users module and the api stats handler to SQLite."""
    monkeypatch.setattr(users_mod, "async_session_factory", sf)
    monkeypatch.setattr(api_mod, "async_session_factory", sf)
