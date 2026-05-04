import logging
import uuid
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, update

from .ai_generator import generate_message
from .database import async_session_factory
from .models import ScheduledTask
from .telegram_client import get_recipient_info, send_message_as_user

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")


async def _execute_job(task_id: int) -> None:
    """Called by APScheduler for each scheduled message."""
    async with async_session_factory() as session:
        task = await session.get(ScheduledTask, task_id)
        if task is None or not task.is_active:
            return

    try:
        recipient_info = await get_recipient_info(task.target_username)
        text = await generate_message(
            task.target_username, task.topic, task.language, recipient_info
        )
        await send_message_as_user(task.target_username, text)

        async with async_session_factory() as session:
            await session.execute(
                update(ScheduledTask)
                .where(ScheduledTask.id == task_id)
                .values(last_sent_at=datetime.now(tz=UTC))
            )
            await session.commit()

        logger.info("Job %s: sent to %s", task.job_id, task.target_username)
    except Exception:
        logger.exception("Job %s failed", task_id)


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
    """On startup, restore all active jobs from the database."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(ScheduledTask).where(ScheduledTask.is_active == True)  # noqa: E712
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
        job_id=job_id,
        is_active=True,
    )

    async with async_session_factory() as session:
        session.add(task)
        await session.commit()
        await session.refresh(task)

    _add_apscheduler_job(task)
    return task


async def cancel_task(task_id: int, user_telegram_id: int) -> bool:
    """Deactivate a task and remove it from APScheduler.

    Returns False if the task doesn't exist or belongs to a different user.
    """
    async with async_session_factory() as session:
        task = await session.get(ScheduledTask, task_id)
        if task is None or task.user_telegram_id != user_telegram_id:
            return False
        task.is_active = False
        await session.commit()
        job_id = task.job_id

    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    return True


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
