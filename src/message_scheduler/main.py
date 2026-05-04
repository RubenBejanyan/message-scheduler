"""
Entry point for the Message Scheduler bot.

Run with:
    uv run python -m message_scheduler.main
"""

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from .bot.handlers import router
from .config import settings
from .database import init_db, run_migrations
from .scheduler import reload_jobs_from_db, scheduler, set_bot
from .telegram_client import start_client, stop_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def _init_db_with_retry(attempts: int = 5, delay: float = 4.0) -> None:
    for attempt in range(1, attempts + 1):
        try:
            await init_db()
            return
        except Exception as exc:
            if attempt == attempts:
                raise
            logger.warning(
                "DB connect attempt %d/%d failed (%s) — retrying in %.0fs…",
                attempt, attempts, exc, delay,
            )
            await asyncio.sleep(delay)


async def main() -> None:
    logger.info("Starting Message Scheduler…")

    logger.info("Initialising database…")
    await _init_db_with_retry()
    await run_migrations()

    logger.info("Connecting Telethon user client…")
    try:
        await start_client()
    except Exception as exc:
        logger.error(
            "Telethon failed to start: %s\n"
            "Run 'uv run python setup_session.py' first to authenticate your account.",
            exc,
        )
        return

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
    dp = Dispatcher(storage=MemoryStorage())
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
        await stop_client()
        await bot.session.close()


if __name__ == "__main__":
    # ProactorEventLoop (Windows default) maps TCP resets to WinError 64 / WinError 10054.
    # SelectorEventLoop raises clean ConnectionResetError instead.
    # loop_factory is the non-deprecated replacement for set_event_loop_policy (removed in 3.16).
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    asyncio.run(main(), loop_factory=loop_factory)
