import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ..config import settings
from ..scheduler import (
    cancel_task,
    create_task,
    get_next_run_time,
    list_active_tasks,
    list_all_active_tasks,
    list_tasks_by_users,
    parse_interval,
)
from ..users import (
    block_user,
    get_user,
    list_active_users,
    list_blocked_users,
    register_user,
    unblock_user,
)
from .keyboards import (
    block_keyboard,
    cancel_task_keyboard,
    confirm_keyboard,
    language_keyboard,
    randomization_keyboard,
    unblock_keyboard,
)
from .states import ScheduleForm

logger = logging.getLogger(__name__)
router = Router()

_JITTER_LABELS: dict[int, str] = {
    900: "±15 min",
    3600: "±1 hour",
    7200: "±2 hours",
}

_BOT_SEND_NOTICE = (
    "\n\n<i>ℹ️ Messages are sent from the bot account. "
    "Recipients must have previously started a conversation with this bot, "
    "or it must be a group/channel where the bot is already a member.</i>"
)


def _is_admin(message: Message) -> bool:
    return message.from_user is not None and message.from_user.id == settings.telegram_admin_id


async def _is_approved(user_id: int) -> bool:
    if user_id == settings.telegram_admin_id:
        return True
    user = await get_user(user_id)
    return user is not None and user.is_approved


def _parse_jitter_text(raw: str) -> int | None | str:
    t = raw.strip().lower()
    if t in ("none", "no", "0", "off", "never"):
        return None
    for suffix, mult in (("h", 3600), ("m", 60)):
        if t.endswith(suffix):
            try:
                return int(t[:-1]) * mult
            except ValueError:
                return "invalid"
    try:
        return int(t) * 60
    except ValueError:
        return "invalid"


# ── /start  /help ─────────────────────────────────────────────────────────────


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    if message.from_user is None:
        return

    uid = message.from_user.id
    user = await register_user(
        telegram_id=uid,
        first_name=message.from_user.first_name or "Unknown",
        username=message.from_user.username,
    )

    if not user.is_approved:
        await message.answer("You have been blocked from using this bot.")
        return

    await message.answer(
        "👋 <b>Message Scheduler Bot</b>\n\n"
        "I generate AI messages and send them on a schedule.\n\n"
        "Commands:\n"
        "/schedule — create a new scheduled message\n"
        "/list — view your active schedules\n"
        "/cancel — cancel a schedule\n"
        "/help — show this message",
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await cmd_start(message)


# ── /users (admin only) ───────────────────────────────────────────────────────


@router.message(Command("users"))
async def cmd_users(message: Message) -> None:
    if not _is_admin(message):
        return

    active = await list_active_users()
    blocked = await list_blocked_users()

    if not active and not blocked:
        await message.answer("No registered users yet.")
        return

    all_ids = [u.telegram_id for u in active + blocked]
    user_tasks = await list_tasks_by_users(all_ids)

    def _schedule_lines(telegram_id: int) -> str:
        tasks = user_tasks.get(telegram_id, [])
        if not tasks:
            return "  🗓 No active schedules"
        lines = [f"  🗓 {len(tasks)} active schedule(s):"]
        for t in tasks:
            last = t.last_sent_at.strftime("%m-%d %H:%M") if t.last_sent_at else "never"
            nrt = get_next_run_time(t.job_id)
            next_run = nrt.strftime("%m-%d %H:%M") if nrt else "—"
            lines.append(
                f"    • #{t.id} → <code>{t.target_username}</code> | {t.interval_label}"
                f" | {t.language}\n"
                f"      topic: <i>{t.topic}</i>\n"
                f"      last: {last} · next: {next_run}"
            )
        return "\n".join(lines)

    if active:
        await message.answer(f"<b>Active users ({len(active)})</b>", parse_mode="HTML")
        for u in active:
            display = f"@{u.username}" if u.username else u.first_name
            await message.answer(
                f"• {u.first_name} {display} — <code>{u.telegram_id}</code>\n"
                f"{_schedule_lines(u.telegram_id)}",
                reply_markup=block_keyboard(u.telegram_id),
                parse_mode="HTML",
            )

    if blocked:
        await message.answer(f"<b>Blocked users ({len(blocked)})</b>", parse_mode="HTML")
        for u in blocked:
            display = f"@{u.username}" if u.username else u.first_name
            await message.answer(
                f"• {u.first_name} {display} — <code>{u.telegram_id}</code>\n"
                f"{_schedule_lines(u.telegram_id)}",
                reply_markup=unblock_keyboard(u.telegram_id),
                parse_mode="HTML",
            )


@router.callback_query(F.data.startswith("block_user:"))
async def cb_block_user(callback: CallbackQuery, bot: Bot) -> None:
    if not callback.from_user or callback.from_user.id != settings.telegram_admin_id:
        await callback.answer("Admin only.", show_alert=True)
        return

    target_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    user = await get_user(target_id)
    name = user.first_name if user else str(target_id)
    await block_user(target_id)

    await callback.message.edit_reply_markup()  # type: ignore[union-attr]
    await callback.message.answer(f"🚫 Blocked {name} ({target_id}).")  # type: ignore[union-attr]
    try:
        await bot.send_message(chat_id=target_id, text="You have been blocked from using this bot.")
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("unblock_user:"))
async def cb_unblock_user(callback: CallbackQuery, bot: Bot) -> None:
    if not callback.from_user or callback.from_user.id != settings.telegram_admin_id:
        await callback.answer("Admin only.", show_alert=True)
        return

    target_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    user = await get_user(target_id)
    name = user.first_name if user else str(target_id)
    await unblock_user(target_id)

    await callback.message.edit_reply_markup()  # type: ignore[union-attr]
    await callback.message.answer(f"✅ Unblocked {name} ({target_id}).")  # type: ignore[union-attr]
    try:
        await bot.send_message(
            chat_id=target_id,
            text="Your access has been restored. Use /schedule to get started.",
        )
    except Exception:
        pass
    await callback.answer()


# ── /schedule wizard ──────────────────────────────────────────────────────────


@router.message(Command("schedule"))
async def cmd_schedule(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return
    if not await _is_approved(message.from_user.id):
        await message.answer("You don't have access to this bot.")
        return
    await state.clear()
    await state.set_state(ScheduleForm.waiting_for_target)
    await message.answer(
        "Step 1 — <b>Who should receive the messages?</b>\n\n"
        "Enter a Telegram @username or group @handle:\n"
        "• <code>@john_doe</code> — private user\n"
        "• <code>@my_group</code> — group or channel",
        parse_mode="HTML",
    )


@router.message(ScheduleForm.waiting_for_target)
async def process_target(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not await _is_approved(message.from_user.id):
        return
    text = (message.text or "").strip()
    if not text.startswith("@") or len(text) < 2:
        await message.answer("Please enter a valid @username or @group handle.")
        return
    await state.update_data(target=text)
    await state.set_state(ScheduleForm.waiting_for_interval)
    await message.answer(
        "Step 2 — <b>How often / when should I send?</b>\n\n"
        "• <code>30m</code> — every 30 minutes\n"
        "• <code>2h</code> — every 2 hours\n"
        "• <code>1d</code> — every day\n"
        "• <code>daily 09:00</code> — every day at 09:00 UTC\n"
        "• <code>window 15:15-15:50</code> — daily at a random time in that range",
        parse_mode="HTML",
    )


@router.message(ScheduleForm.waiting_for_interval)
async def process_interval(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not await _is_approved(message.from_user.id):
        return
    text = (message.text or "").strip()
    parsed = parse_interval(text)

    if parsed is None:
        await message.answer(
            "Could not parse that. Try: <code>30m</code>, <code>2h</code>, "
            "<code>daily 09:00</code>, or <code>window 15:00-15:45</code>",
            parse_mode="HTML",
        )
        return

    interval_type, interval_value, interval_label = parsed

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

    if interval_type == "window":
        await state.update_data(jitter_seconds=None)
        await state.set_state(ScheduleForm.waiting_for_language)
        await message.answer(
            "Step 3 — <b>Language?</b>\n\nChoose the language for the generated messages:",
            reply_markup=language_keyboard(),
            parse_mode="HTML",
        )
    else:
        await state.set_state(ScheduleForm.waiting_for_randomization)
        await message.answer(
            "Step 3 — <b>Randomization</b>\n\n"
            "Add a random delay so messages don't always arrive at the exact same time.\n\n"
            "Pick a preset or type a custom amount (e.g. <code>45m</code>, <code>3h</code>, "
            "<code>90</code> for 90 minutes):",
            reply_markup=randomization_keyboard(),
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("jitter:"), ScheduleForm.waiting_for_randomization)
async def process_randomization(callback: CallbackQuery, state: FSMContext) -> None:
    raw = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    jitter = raw if raw > 0 else None
    await state.update_data(jitter_seconds=jitter)
    await callback.message.edit_reply_markup()  # type: ignore[union-attr]
    await state.set_state(ScheduleForm.waiting_for_language)
    await callback.message.answer(  # type: ignore[union-attr]
        "Step 4 — <b>Language?</b>\n\nChoose the language for the generated messages:",
        reply_markup=language_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(ScheduleForm.waiting_for_randomization)
async def process_randomization_text(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not await _is_approved(message.from_user.id):
        return
    result = _parse_jitter_text((message.text or "").strip())
    if result == "invalid":
        await message.answer(
            "Could not parse that. Use a preset button or type e.g. "
            "<code>45m</code>, <code>3h</code>, <code>90</code> (minutes), or <code>none</code>.",
            parse_mode="HTML",
        )
        return
    jitter: int | None = result  # type: ignore[assignment]
    await state.update_data(jitter_seconds=jitter)
    await state.set_state(ScheduleForm.waiting_for_language)
    await message.answer(
        "Step 4 — <b>Language?</b>\n\nChoose the language for the generated messages:",
        reply_markup=language_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("lang:"), ScheduleForm.waiting_for_language)
async def process_language(callback: CallbackQuery, state: FSMContext) -> None:
    language = callback.data.split(":")[1]  # type: ignore[union-attr]
    await state.update_data(language=language)
    await callback.message.edit_reply_markup()  # type: ignore[union-attr]

    data = await state.get_data()
    step = "5" if data.get("interval_type") != "window" else "4"
    await state.set_state(ScheduleForm.waiting_for_topic)
    await callback.message.answer(  # type: ignore[union-attr]
        f"Step {step} — <b>What should the messages be about?</b>\n\n"
        "Describe the topic or context (e.g. <i>good morning motivation</i>, "
        "<i>remind her to drink water</i>):",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(ScheduleForm.waiting_for_topic)
async def process_topic(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not await _is_approved(message.from_user.id):
        return
    topic = (message.text or "").strip()
    if len(topic) < 3:
        await message.answer("Please provide a more descriptive topic.")
        return

    await state.update_data(topic=topic)
    data = await state.get_data()
    await state.set_state(ScheduleForm.waiting_for_confirm)

    jitter = data.get("jitter_seconds")
    jitter_line = (
        f"• Randomization: {_JITTER_LABELS.get(jitter, f'+{jitter}s')}\n" if jitter else ""
    )

    await message.answer(
        "📋 <b>Confirm your schedule:</b>\n\n"
        f"• Recipient: <code>{data['target']}</code>\n"
        f"• Frequency: {data['interval_label']}\n"
        f"{jitter_line}"
        f"• Language: {data.get('language', 'English')}\n"
        f"• Topic: <i>{topic}</i>\n\n"
        f"Ready to activate?{_BOT_SEND_NOTICE}",
        reply_markup=confirm_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "confirm_yes", ScheduleForm.waiting_for_confirm)
async def confirm_yes(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user is None:
        return
    data = await state.get_data()
    await state.clear()
    await callback.message.edit_reply_markup()  # type: ignore[union-attr]

    jitter: int | None = data.get("jitter_seconds")
    language: str = data.get("language", "English")

    interval_label = data["interval_label"]
    if jitter:
        interval_label += f" ({_JITTER_LABELS.get(jitter, f'+{jitter}s')} randomization)"

    try:
        task = await create_task(
            user_telegram_id=callback.from_user.id,
            target_username=data["target"],
            topic=data["topic"],
            interval_type=data["interval_type"],
            interval_value=data["interval_value"],
            interval_label=interval_label,
            jitter_seconds=jitter,
            language=language,
        )
        await callback.message.answer(  # type: ignore[union-attr]
            f"✅ Schedule created! (ID: <code>{task.id}</code>)\n"
            f"Sending to {task.target_username} — {task.interval_label} — {task.language}.",
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
    if message.from_user is None:
        return
    if not await _is_approved(message.from_user.id):
        await message.answer("You don't have access to this bot.")
        return

    uid = message.from_user.id
    is_admin = uid == settings.telegram_admin_id
    tasks = await list_all_active_tasks() if is_admin else await list_active_tasks(uid)

    if not tasks:
        await message.answer("No active schedules. Use /schedule to create one.")
        return

    for task in tasks:
        last = task.last_sent_at.strftime("%Y-%m-%d %H:%M UTC") if task.last_sent_at else "never"
        nrt = get_next_run_time(task.job_id)
        next_run = nrt.strftime("%Y-%m-%d %H:%M UTC") if nrt else "—"
        owner_line = (
            f"• Owner: <code>{task.user_telegram_id or 'unknown (legacy)'}</code>\n"
            if is_admin
            else ""
        )
        text = (
            f"🗓 <b>Schedule #{task.id}</b>\n"
            f"{owner_line}"
            f"• To: <code>{task.target_username}</code>\n"
            f"• Frequency: {task.interval_label}\n"
            f"• Language: {task.language}\n"
            f"• Topic: <i>{task.topic}</i>\n"
            f"• Last sent: {last}\n"
            f"• Next run: {next_run}"
        )
        await message.answer(text, reply_markup=cancel_task_keyboard(task.id), parse_mode="HTML")


# ── /cancel ───────────────────────────────────────────────────────────────────


@router.message(Command("cancel"))
async def cmd_cancel(message: Message) -> None:
    if message.from_user is None:
        return
    if not await _is_approved(message.from_user.id):
        return
    await message.answer("Use the 🗑 buttons in /list to cancel a specific schedule.")


@router.callback_query(F.data.startswith("cancel_task:"))
async def cancel_task_callback(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        return
    task_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    uid = callback.from_user.id
    is_admin = uid == settings.telegram_admin_id
    success = await cancel_task(task_id, uid, force=is_admin)
    await callback.message.edit_reply_markup()  # type: ignore[union-attr]
    if success:
        await callback.message.answer(f"🗑 Schedule #{task_id} cancelled.")  # type: ignore[union-attr]
    else:
        await callback.message.answer(f"Schedule #{task_id} not found.")  # type: ignore[union-attr]
    await callback.answer()
