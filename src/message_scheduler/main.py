"""
Entry point for the Message Scheduler bot.

Run with:
    uv run python -m message_scheduler.main
"""

import asyncio
import logging
import sys
import time

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand

from .bot.handlers import router
from .config import settings
from .scheduler import reload_jobs_from_db, scheduler, set_bot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def _run_migrations(attempts: int = 5, delay: float = 4.0) -> None:
    """Run Alembic migrations synchronously before the async app starts."""
    from alembic.config import Config

    from alembic import command

    cfg = Config("alembic.ini")
    for attempt in range(1, attempts + 1):
        try:
            command.upgrade(cfg, "head")
            return
        except Exception as exc:
            if attempt == attempts:
                raise
            logger.warning(
                "Migration attempt %d/%d failed (%s) — retrying in %.0fs…",
                attempt, attempts, exc, delay,
            )
            time.sleep(delay)


async def main() -> None:
    logger.info("Starting Message Scheduler…")

    logger.info("Starting APScheduler…")
    scheduler.start()
    await reload_jobs_from_db()

    logger.info("Starting Telegram bot…")
    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    set_bot(bot)
    await bot.set_my_commands([
        BotCommand(command="schedule", description="Create a new scheduled message"),
        BotCommand(command="list", description="View your active schedules"),
        BotCommand(command="cancel", description="Cancel a schedule"),
        BotCommand(command="help", description="Help & all commands"),
    ])
    dp = Dispatcher(storage=RedisStorage.from_url(settings.redis_url))
    dp.include_router(router)

    try:
        while True:
            try:
                await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
                break
            except (ConnectionResetError, OSError) as exc:
                logger.warning("Polling connection reset (%s) — reconnecting in 5s…", exc)
                await asyncio.sleep(5)
    finally:
        logger.info("Shutting down…")
        scheduler.shutdown(wait=False)
        await bot.session.close()


if __name__ == "__main__":
    logger.info("Running database migrations…")
    _run_migrations()

    # ProactorEventLoop (Windows default) maps TCP resets to WinError 64 / WinError 10054.
    # SelectorEventLoop raises clean ConnectionResetError instead.
    # loop_factory is the non-deprecated replacement for set_event_loop_policy (removed in 3.16).
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    asyncio.run(main(), loop_factory=loop_factory)
