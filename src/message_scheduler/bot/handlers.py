import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ..config import settings
from ..scheduler import cancel_task, create_task, list_active_tasks, parse_interval
from .keyboards import cancel_task_keyboard, confirm_keyboard
from .states import ScheduleForm

logger = logging.getLogger(__name__)
router = Router()


def _owner_only(message: Message) -> bool:
    """Return True if message comes from the configured owner."""
    return message.from_user is not None and message.from_user.id == settings.telegram_owner_id


# ── Guards ────────────────────────────────────────────────────────────────────


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    if not _owner_only(message):
        return
    await message.answer(
        "👋 <b>Message Scheduler Bot</b>\n\n"
        "I generate AI messages and send them <i>from your account</i> on a schedule.\n\n"
        "Commands:\n"
        "/schedule — create a new scheduled message\n"
        "/list — view active schedules\n"
        "/cancel — cancel a schedule\n"
        "/help — show this message",
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    if not _owner_only(message):
        return
    await cmd_start(message)


# ── /schedule wizard ──────────────────────────────────────────────────────────


@router.message(Command("schedule"))
async def cmd_schedule(message: Message, state: FSMContext) -> None:
    if not _owner_only(message):
        return
    await state.clear()
    await state.set_state(ScheduleForm.waiting_for_target)
    await message.answer(
        "Step 1/3 — <b>Who should receive the messages?</b>\n\n"
        "Enter the Telegram username (e.g. <code>@john_doe</code>):",
        parse_mode="HTML",
    )


@router.message(ScheduleForm.waiting_for_target)
async def process_target(message: Message, state: FSMContext) -> None:
    if not _owner_only(message):
        return
    text = (message.text or "").strip()
    if not text.startswith("@") or len(text) < 2:
        await message.answer("Please enter a valid username starting with @")
        return

    await state.update_data(target=text)
    await state.set_state(ScheduleForm.waiting_for_interval)
    await message.answer(
        "Step 2/3 — <b>How often should I send?</b>\n\n"
        "Examples:\n"
        "• <code>30m</code> — every 30 minutes\n"
        "• <code>2h</code> — every 2 hours\n"
        "• <code>1d</code> — every day\n"
        "• <code>daily 09:00</code> — every day at 09:00 UTC",
        parse_mode="HTML",
    )


@router.message(ScheduleForm.waiting_for_interval)
async def process_interval(message: Message, state: FSMContext) -> None:
    if not _owner_only(message):
        return
    text = (message.text or "").strip()
    parsed = parse_interval(text)

    if parsed is None:
        await message.answer(
            "Could not parse that interval. Try formats like: 30m, 2h, 1d, daily 09:00"
        )
        return

    interval_type, interval_value, interval_label = parsed

    # Enforce minimum interval
    if interval_type == "interval":
        min_seconds = settings.min_interval_minutes * 60
        if int(interval_value) < min_seconds:
            await message.answer(
                f"Minimum interval is {settings.min_interval_minutes} minutes. Please try again."
            )
            return

    await state.update_data(
        interval_type=interval_type,
        interval_value=interval_value,
        interval_label=interval_label,
    )
    await state.set_state(ScheduleForm.waiting_for_topic)
    await message.answer(
        "Step 3/3 — <b>What should the message be about?</b>\n\n"
        "Describe the topic or context (e.g. <i>good morning motivation</i>, "
        "<i>remind her to drink water</i>, <i>funny cat fact</i>):",
        parse_mode="HTML",
    )


@router.message(ScheduleForm.waiting_for_topic)
async def process_topic(message: Message, state: FSMContext) -> None:
    if not _owner_only(message):
        return
    topic = (message.text or "").strip()
    if len(topic) < 3:
        await message.answer("Please provide a more descriptive topic.")
        return

    await state.update_data(topic=topic)
    data = await state.get_data()
    await state.set_state(ScheduleForm.waiting_for_confirm)

    await message.answer(
        "📋 <b>Confirm your schedule:</b>\n\n"
        f"• Recipient: <code>{data['target']}</code>\n"
        f"• Frequency: {data['interval_label']}\n"
        f"• Topic: <i>{topic}</i>\n\n"
        "Ready to activate?",
        reply_markup=confirm_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "confirm_yes", ScheduleForm.waiting_for_confirm)
async def confirm_yes(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    await callback.message.edit_reply_markup()  # type: ignore[union-attr]

    try:
        task = await create_task(
            target_username=data["target"],
            topic=data["topic"],
            interval_type=data["interval_type"],
            interval_value=data["interval_value"],
            interval_label=data["interval_label"],
        )
        await callback.message.answer(  # type: ignore[union-attr]
            f"✅ Schedule created! (ID: <code>{task.id}</code>)\n"
            f"I'll send messages to {task.target_username} {task.interval_label}.",
            parse_mode="HTML",
        )
    except Exception:
        logger.exception("Failed to create task")
        await callback.message.answer("❌ Failed to create schedule. Check logs.")  # type: ignore[union-attr]

    await callback.answer()


@router.callback_query(F.data == "confirm_no", ScheduleForm.waiting_for_confirm)
async def confirm_no(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_reply_markup()  # type: ignore[union-attr]
    await callback.message.answer("Cancelled. Use /schedule to start over.")  # type: ignore[union-attr]
    await callback.answer()


# ── /list ────────────────────────────────────────────────────────────────────


@router.message(Command("list"))
async def cmd_list(message: Message) -> None:
    if not _owner_only(message):
        return
    tasks = await list_active_tasks()
    if not tasks:
        await message.answer("No active schedules. Use /schedule to create one.")
        return

    for task in tasks:
        last = task.last_sent_at.strftime("%Y-%m-%d %H:%M UTC") if task.last_sent_at else "never"
        text = (
            f"🗓 <b>Schedule #{task.id}</b>\n"
            f"• To: <code>{task.target_username}</code>\n"
            f"• Frequency: {task.interval_label}\n"
            f"• Topic: <i>{task.topic}</i>\n"
            f"• Last sent: {last}"
        )
        await message.answer(
            text,
            reply_markup=cancel_task_keyboard(task.id),
            parse_mode="HTML",
        )


# ── /cancel ───────────────────────────────────────────────────────────────────


@router.message(Command("cancel"))
async def cmd_cancel(message: Message) -> None:
    if not _owner_only(message):
        return
    await message.answer("Use the 🗑 buttons in /list to cancel a specific schedule.")


@router.callback_query(F.data.startswith("cancel_task:"))
async def cancel_task_callback(callback: CallbackQuery) -> None:
    task_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    success = await cancel_task(task_id)
    await callback.message.edit_reply_markup()  # type: ignore[union-attr]
    if success:
        await callback.message.answer(f"🗑 Schedule #{task_id} cancelled.")  # type: ignore[union-attr]
    else:
        await callback.message.answer(f"Schedule #{task_id} not found.")  # type: ignore[union-attr]
    await callback.answer()
