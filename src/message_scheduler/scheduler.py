import json
import logging
import random
import uuid
from datetime import UTC, datetime
from typing import cast

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import func, select, update

from .ai_generator import generate_message
from .config import settings
from .database import async_session_factory
from .models import ScheduledTask, SentMessage

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")

_bot: Bot | None = None


def set_bot(bot: Bot) -> None:
    global _bot
    _bot = bot


async def _record_sent(task: ScheduledTask, text: str) -> None:
    async with async_session_factory() as session:
        session.add(
            SentMessage(
                task_id=task.id,
                user_telegram_id=task.user_telegram_id,
                target_username=task.target_username,
                content=text,
            )
        )
        await session.commit()


async def _notify_owner(uid: int, text: str) -> None:
    if _bot is None:
        return
    try:
        await _bot.send_message(chat_id=uid, text=text, parse_mode="HTML")
    except Exception:
        logger.warning("Could not deliver owner notification to %d", uid)


async def _build_message(task: ScheduledTask) -> str:
    if task.message_mode == "exact" and task.messages_json:
        return str(random.choice(json.loads(task.messages_json)))
    return await generate_message(task.target_username, task.topic, task.language)


async def _execute_job(task_id: int) -> None:
    """Called by APScheduler for each scheduled message."""
    async with async_session_factory() as session:
        task = await session.get(ScheduledTask, task_id)
        if task is None or not task.is_active or task.is_paused:
            return
    # task attributes remain accessible (expire_on_commit=False)

    try:
        text = await _build_message(task)
        if _bot is None:
            raise RuntimeError("Bot instance not set — call set_bot() on startup")
        await _bot.send_message(chat_id=task.target_username, text=text)

        prev_failures = task.consecutive_failures
        async with async_session_factory() as session:
            await session.execute(
                update(ScheduledTask)
                .where(ScheduledTask.id == task_id)
                .values(
                    last_sent_at=datetime.now(tz=UTC),
                    consecutive_failures=0,
                    last_error=None,
                )
            )
            await session.commit()

        await _record_sent(task, text)
        logger.info("Job %s: sent to %s", task.job_id, task.target_username)

        if prev_failures > 0 and task.user_telegram_id:
            await _notify_owner(
                task.user_telegram_id,
                f"✅ <b>Schedule #{task_id} recovered</b>\n"
                f"Delivered to <code>{task.target_username}</code> "
                f"(was failing for {prev_failures} attempt(s)).",
            )

    except Exception as exc:
        failures = task.consecutive_failures + 1
        error_str = str(exc)[:500]

        async with async_session_factory() as session:
            await session.execute(
                update(ScheduledTask)
                .where(ScheduledTask.id == task_id)
                .values(consecutive_failures=failures, last_error=error_str)
            )
            await session.commit()

        logger.exception("Job %s failed (consecutive #%d)", task_id, failures)

        if failures >= settings.max_consecutive_failures:
            async with async_session_factory() as session:
                await session.execute(
                    update(ScheduledTask)
                    .where(ScheduledTask.id == task_id)
                    .values(is_paused=True)
                )
                await session.commit()
            if scheduler.get_job(task.job_id):
                scheduler.remove_job(task.job_id)
            if task.user_telegram_id:
                await _notify_owner(
                    task.user_telegram_id,
                    f"⏸ <b>Schedule #{task_id} auto-paused</b>\n"
                    f"Failed {failures} times in a row sending to "
                    f"<code>{task.target_username}</code>.\n\n"
                    f"Use /list to review and resume.",
                )
        elif task.user_telegram_id and (failures == 1 or failures % 5 == 0):
            await _notify_owner(
                task.user_telegram_id,
                f"⚠️ <b>Schedule #{task_id} failed</b> (×{failures})\n"
                f"→ <code>{task.target_username}</code>\n\n"
                f"<i>{error_str[:200]}</i>",
            )


async def fire_task_now(task_id: int) -> str:
    """Generate and immediately send the message for a task. Returns the sent text."""
    async with async_session_factory() as session:
        task = await session.get(ScheduledTask, task_id)
        if task is None or not task.is_active:
            raise ValueError(f"Task #{task_id} not found or inactive")

    text = await _build_message(task)
    if _bot is None:
        raise RuntimeError("Bot instance not set — call set_bot() on startup")
    await _bot.send_message(chat_id=task.target_username, text=text)

    async with async_session_factory() as session:
        await session.execute(
            update(ScheduledTask)
            .where(ScheduledTask.id == task_id)
            .values(last_sent_at=datetime.now(tz=UTC), consecutive_failures=0, last_error=None)
        )
        await session.commit()

    await _record_sent(task, text)
    logger.info("Manual fire for task %d → %s", task_id, task.target_username)
    return text


def _add_apscheduler_job(task: ScheduledTask) -> None:
    """Register a task in APScheduler based on its interval type."""
    jitter = task.jitter_seconds or 0

    if task.interval_type == "interval":
        scheduler.add_job(
            _execute_job,
            "interval",
            seconds=int(task.interval_value),
            jitter=jitter,
            id=task.job_id,
            args=[task.id],
            replace_existing=True,
            misfire_grace_time=60,
        )
    elif task.interval_type == "cron":
        hour, minute = task.interval_value.split(":")
        scheduler.add_job(
            _execute_job,
            "cron",
            hour=int(hour),
            minute=int(minute),
            jitter=jitter,
            id=task.job_id,
            args=[task.id],
            replace_existing=True,
            misfire_grace_time=60,
        )
    elif task.interval_type == "window":
        start_str, end_str = task.interval_value.split("-")
        s_h, s_m = map(int, start_str.split(":"))
        e_h, e_m = map(int, end_str.split(":"))
        window_secs = (e_h * 60 + e_m - s_h * 60 - s_m) * 60
        scheduler.add_job(
            _execute_job,
            "cron",
            hour=s_h,
            minute=s_m,
            jitter=max(0, window_secs),
            id=task.job_id,
            args=[task.id],
            replace_existing=True,
            misfire_grace_time=max(60, window_secs),
        )


async def reload_jobs_from_db() -> None:
    """On startup, restore all active non-paused jobs from the database."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(ScheduledTask).where(
                ScheduledTask.is_active == True,  # noqa: E712
                ScheduledTask.is_paused == False,  # noqa: E712
            )
        )
        tasks = result.scalars().all()

    for task in tasks:
        _add_apscheduler_job(task)
        logger.info(
            "Restored job: %s → %s every %s", task.job_id, task.target_username, task.interval_label
        )


async def create_task(
    user_telegram_id: int,
    target_username: str,
    topic: str,
    interval_type: str,
    interval_value: str,
    interval_label: str,
    jitter_seconds: int | None = None,
    language: str = "English",
    message_mode: str = "ai",
    messages_json: str | None = None,
) -> ScheduledTask:
    """Persist a new scheduled task and register it with APScheduler."""
    job_id = f"task_{uuid.uuid4().hex[:12]}"

    task = ScheduledTask(
        user_telegram_id=user_telegram_id,
        target_username=target_username,
        topic=topic,
        interval_type=interval_type,
        interval_value=interval_value,
        interval_label=interval_label,
        jitter_seconds=jitter_seconds,
        language=language,
        message_mode=message_mode,
        messages_json=messages_json,
        job_id=job_id,
        is_active=True,
    )

    async with async_session_factory() as session:
        session.add(task)
        await session.commit()
        await session.refresh(task)

    _add_apscheduler_job(task)
    return task


async def cancel_task(task_id: int, user_telegram_id: int, force: bool = False) -> bool:
    """Deactivate a task and remove it from APScheduler.

    Returns False if the task doesn't exist or belongs to a different user.
    Pass force=True (admin only) to bypass ownership check.
    """
    async with async_session_factory() as session:
        task = await session.get(ScheduledTask, task_id)
        if task is None:
            return False
        if not force and task.user_telegram_id != user_telegram_id:
            return False
        task.is_active = False
        await session.commit()
        job_id = task.job_id

    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    return True


async def pause_task(task_id: int, user_telegram_id: int, force: bool = False) -> bool:
    """Pause a task: keeps it in DB but removes it from APScheduler."""
    async with async_session_factory() as session:
        task = await session.get(ScheduledTask, task_id)
        if task is None or not task.is_active or task.is_paused:
            return False
        if not force and task.user_telegram_id != user_telegram_id:
            return False
        task.is_paused = True
        await session.commit()
        job_id = task.job_id

    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    return True


async def resume_task(task_id: int, user_telegram_id: int, force: bool = False) -> bool:
    """Resume a paused task: re-registers it with APScheduler."""
    async with async_session_factory() as session:
        task = await session.get(ScheduledTask, task_id)
        if task is None or not task.is_active or not task.is_paused:
            return False
        if not force and task.user_telegram_id != user_telegram_id:
            return False
        task.is_paused = False
        await session.commit()
    # expire_on_commit=False — task attributes still valid after session closes
    _add_apscheduler_job(task)
    return True


async def count_user_tasks(user_telegram_id: int) -> int:
    """Count non-cancelled schedules for a user (active + paused)."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(func.count()).select_from(ScheduledTask).where(
                ScheduledTask.user_telegram_id == user_telegram_id,
                ScheduledTask.is_active == True,  # noqa: E712
            )
        )
        return result.scalar() or 0


async def update_task_topic(
    task_id: int, user_telegram_id: int, topic: str, force: bool = False
) -> bool:
    async with async_session_factory() as session:
        task = await session.get(ScheduledTask, task_id)
        if task is None or not task.is_active:
            return False
        if not force and task.user_telegram_id != user_telegram_id:
            return False
        task.topic = topic
        await session.commit()
    return True


async def update_task_language(
    task_id: int, user_telegram_id: int, language: str, force: bool = False
) -> bool:
    async with async_session_factory() as session:
        task = await session.get(ScheduledTask, task_id)
        if task is None or not task.is_active:
            return False
        if not force and task.user_telegram_id != user_telegram_id:
            return False
        task.language = language
        await session.commit()
    return True


async def update_task_interval(
    task_id: int,
    user_telegram_id: int,
    interval_type: str,
    interval_value: str,
    interval_label: str,
    force: bool = False,
) -> bool:
    async with async_session_factory() as session:
        task = await session.get(ScheduledTask, task_id)
        if task is None or not task.is_active:
            return False
        if not force and task.user_telegram_id != user_telegram_id:
            return False
        task.interval_type = interval_type
        task.interval_value = interval_value
        task.interval_label = interval_label
        await session.commit()
    # expire_on_commit=False — task attributes still valid after session closes
    if not task.is_paused:
        _add_apscheduler_job(task)
    return True


async def update_task_messages(
    task_id: int, user_telegram_id: int, messages_json: str, force: bool = False
) -> bool:
    async with async_session_factory() as session:
        task = await session.get(ScheduledTask, task_id)
        if task is None or not task.is_active or task.message_mode != "exact":
            return False
        if not force and task.user_telegram_id != user_telegram_id:
            return False
        task.messages_json = messages_json
        task.topic = json.loads(messages_json)[0][:100]
        await session.commit()
    return True


async def get_task_history(task_id: int, limit: int = 5) -> list[SentMessage]:
    """Return the most recent sent messages for a task, newest first."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(SentMessage)
            .where(SentMessage.task_id == task_id)
            .order_by(SentMessage.sent_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


async def get_task(task_id: int) -> ScheduledTask | None:
    async with async_session_factory() as session:
        return await session.get(ScheduledTask, task_id)


async def list_active_tasks(user_telegram_id: int) -> list[ScheduledTask]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(ScheduledTask)
            .where(
                ScheduledTask.is_active == True,  # noqa: E712
                ScheduledTask.user_telegram_id == user_telegram_id,
            )
            .order_by(ScheduledTask.created_at)
        )
        return list(result.scalars().all())


async def list_all_active_tasks() -> list[ScheduledTask]:
    """Admin: all active tasks regardless of owner (catches NULL user_telegram_id zombies)."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(ScheduledTask)
            .where(ScheduledTask.is_active == True)  # noqa: E712
            .order_by(ScheduledTask.created_at)
        )
        return list(result.scalars().all())


async def list_tasks_by_users(telegram_ids: list[int]) -> dict[int, list[ScheduledTask]]:
    """Return {telegram_id: [active tasks]} for a batch of users in one query."""
    if not telegram_ids:
        return {}
    async with async_session_factory() as session:
        result = await session.execute(
            select(ScheduledTask)
            .where(
                ScheduledTask.is_active == True,  # noqa: E712
                ScheduledTask.user_telegram_id.in_(telegram_ids),
            )
            .order_by(ScheduledTask.user_telegram_id, ScheduledTask.created_at)
        )
        tasks = result.scalars().all()
    grouped: dict[int, list[ScheduledTask]] = {tid: [] for tid in telegram_ids}
    for task in tasks:
        grouped[task.user_telegram_id].append(task)
    return grouped


def get_next_run_time(job_id: str) -> datetime | None:
    """Return APScheduler's next_run_time for the given job, or None if not found."""
    job = scheduler.get_job(job_id)
    if job is None:
        return None
    return cast(datetime | None, job.next_run_time)


def parse_interval(text: str) -> tuple[str, str, str] | None:
    """
    Parse user input into (interval_type, interval_value, interval_label).
    Returns None if input is invalid.

    Accepted formats:
        30m              → every 30 minutes
        2h               → every 2 hours
        1d               → every 1 day
        daily 09:00      → every day at 09:00 UTC
        window 15:15-15:50 → daily at random time between 15:15 and 15:50 UTC
    """
    text = text.strip().lower()

    if text.startswith("window "):
        window_part = text[7:].strip()
        try:
            start_str, end_str = window_part.split("-")
            s_h, s_m = map(int, start_str.strip().split(":"))
            e_h, e_m = map(int, end_str.strip().split(":"))
            if not (0 <= s_h <= 23 and 0 <= s_m <= 59 and 0 <= e_h <= 23 and 0 <= e_m <= 59):
                return None
            if e_h * 60 + e_m <= s_h * 60 + s_m:
                return None
            value = f"{s_h:02d}:{s_m:02d}-{e_h:02d}:{e_m:02d}"
            label = f"daily between {s_h:02d}:{s_m:02d} and {e_h:02d}:{e_m:02d} UTC"
            return ("window", value, label)
        except ValueError:
            return None

    if text.startswith("daily "):
        time_part = text[6:].strip()
        try:
            hour, minute = time_part.split(":")
            hour_int, minute_int = int(hour), int(minute)
            if not (0 <= hour_int <= 23 and 0 <= minute_int <= 59):
                return None
            value = f"{hour_int:02d}:{minute_int:02d}"
            label = f"daily at {value} UTC"
            return ("cron", value, label)
        except ValueError:
            return None

    suffixes = {"m": 60, "h": 3600, "d": 86400}
    for suffix, multiplier in suffixes.items():
        if text.endswith(suffix):
            try:
                amount = int(text[:-1])
            except ValueError:
                return None
            if amount <= 0:
                return None
            seconds = amount * multiplier
            unit_map = {"m": "minute(s)", "h": "hour(s)", "d": "day(s)"}
            label = f"every {amount} {unit_map[suffix]}"
            return ("interval", str(seconds), label)

    return None
