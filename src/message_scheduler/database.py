from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=300,  # recycle connections every 5 min — guards against WSL2 network drops
)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    """Create all tables on startup."""
    from . import models  # noqa: F401 — import to register mapped classes

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def run_migrations() -> None:
    """Add columns introduced after initial schema creation.

    Uses IF NOT EXISTS so it is safe to run on every startup.
    """
    stmts = [
        "ALTER TABLE scheduled_tasks ADD COLUMN IF NOT EXISTS jitter_seconds INTEGER",
        "ALTER TABLE scheduled_tasks ADD COLUMN IF NOT EXISTS "
        "language VARCHAR(50) NOT NULL DEFAULT 'English'",
        "ALTER TABLE scheduled_tasks ADD COLUMN IF NOT EXISTS user_telegram_id BIGINT",
        # Auto-approve any users left pending from the previous approval-flow version
        "UPDATE registered_users SET is_approved = TRUE WHERE is_approved = FALSE",
        "ALTER TABLE scheduled_tasks ADD COLUMN IF NOT EXISTS "
        "send_as VARCHAR(10) NOT NULL DEFAULT 'bot'",
        "ALTER TABLE registered_users ADD COLUMN IF NOT EXISTS "
        "has_telethon_session BOOLEAN NOT NULL DEFAULT FALSE",
    ]
    async with engine.begin() as conn:
        for stmt in stmts:
            await conn.execute(text(stmt))


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session
