import json
import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ..config import settings
from ..scheduler import (
    cancel_task,
    count_user_tasks,
    create_task,
    fire_task_now,
    get_next_run_time,
    get_task,
    get_task_history,
    list_active_tasks,
    list_all_active_tasks,
    list_tasks_by_users,
    parse_interval,
    pause_task,
    resume_task,
    update_task_interval,
    update_task_language,
    update_task_messages,
    update_task_topic,
)
from ..users import (
    block_user,
    get_user,
    grant_admin,
    list_active_users,
    list_blocked_users,
    register_user,
    revoke_admin,
    unblock_user,
)
from .keyboards import (
    active_user_keyboard,
    confirm_keyboard,
    edit_field_keyboard,
    edit_language_keyboard,
    language_keyboard,
    message_mode_keyboard,
    randomization_keyboard,
    task_keyboard,
    unblock_keyboard,
)
from .states import EditForm, ScheduleForm

logger = logging.getLogger(__name__)
router = Router()

_JITTER_LABELS: dict[int, str] = {
    900: "±15 min",
    3600: "±1 hour",
    7200: "±2 hours",
}


def _jitter_label(seconds: int) -> str:
    if seconds in _JITTER_LABELS:
        return _JITTER_LABELS[seconds]
    minutes = seconds // 60
    return f"±{minutes} min" if minutes else f"±{seconds}s"

_BOT_SEND_NOTICE = (
    "\n\n<i>ℹ️ Messages are sent from the bot account. "
    "Recipients must have previously started a conversation with this bot, "
    "or it must be a group/channel where the bot is already a member.</i>"
)


def _is_master_admin(user_id: int) -> bool:
    return user_id == settings.telegram_admin_id


async def _is_admin(user_id: int) -> bool:
    """True for both the master admin and any user granted admin via /users."""
    if user_id == settings.telegram_admin_id:
        return True
    user = await get_user(user_id)
    return user is not None and user.is_admin


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
    if message.from_user is None or not _is_master_admin(message.from_user.id):
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
            admin_badge = " 👑" if u.is_admin else ""
            await message.answer(
                f"• {u.first_name} {display}{admin_badge} — <code>{u.telegram_id}</code>\n"
                f"{_schedule_lines(u.telegram_id)}",
                reply_markup=active_user_keyboard(u.telegram_id, u.is_admin),
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
    if not callback.from_user or not _is_master_admin(callback.from_user.id):
        await callback.answer("Master admin only.", show_alert=True)
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
        logger.warning("Could not notify blocked user %d", target_id)
    await callback.answer()


@router.callback_query(F.data.startswith("unblock_user:"))
async def cb_unblock_user(callback: CallbackQuery, bot: Bot) -> None:
    if not callback.from_user or not _is_master_admin(callback.from_user.id):
        await callback.answer("Master admin only.", show_alert=True)
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
        logger.warning("Could not notify unblocked user %d", target_id)
    await callback.answer()


@router.callback_query(F.data.startswith("grant_admin:"))
async def cb_grant_admin(callback: CallbackQuery, bot: Bot) -> None:
    if not callback.from_user or not _is_master_admin(callback.from_user.id):
        await callback.answer("Master admin only.", show_alert=True)
        return
    target_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    if _is_master_admin(target_id):
        await callback.answer("Already master admin.", show_alert=True)
        return
    user = await get_user(target_id)
    name = user.first_name if user else str(target_id)
    await grant_admin(target_id)
    await callback.message.edit_reply_markup()  # type: ignore[union-attr]
    await callback.message.answer(f"👑 {name} ({target_id}) is now an admin.")  # type: ignore[union-attr]
    try:
        await bot.send_message(
            chat_id=target_id,
            text="👑 You have been granted admin permissions for this bot.",
        )
    except Exception:
        logger.warning("Could not notify user %d of admin grant", target_id)
    await callback.answer()


@router.callback_query(F.data.startswith("revoke_admin:"))
async def cb_revoke_admin(callback: CallbackQuery, bot: Bot) -> None:
    if not callback.from_user or not _is_master_admin(callback.from_user.id):
        await callback.answer("Master admin only.", show_alert=True)
        return
    target_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    user = await get_user(target_id)
    name = user.first_name if user else str(target_id)
    await revoke_admin(target_id)
    await callback.message.edit_reply_markup()  # type: ignore[union-attr]
    await callback.message.answer(f"👑 Admin removed from {name} ({target_id}).")  # type: ignore[union-attr]
    try:
        await bot.send_message(
            chat_id=target_id,
            text="Your admin permissions have been revoked.",
        )
    except Exception:
        logger.warning("Could not notify user %d of admin revoke", target_id)
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
        await state.set_state(ScheduleForm.waiting_for_mode)
        await message.answer(
            "Step 3 — <b>What should I send?</b>",
            reply_markup=message_mode_keyboard(),
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
    await state.set_state(ScheduleForm.waiting_for_mode)
    await callback.message.answer(  # type: ignore[union-attr]
        "Step 4 — <b>What should I send?</b>",
        reply_markup=message_mode_keyboard(),
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
    await state.set_state(ScheduleForm.waiting_for_mode)
    await message.answer(
        "Step 4 — <b>What should I send?</b>",
        reply_markup=message_mode_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("mode:"), ScheduleForm.waiting_for_mode)
async def process_mode(callback: CallbackQuery, state: FSMContext) -> None:
    mode = callback.data.split(":")[1]  # type: ignore[union-attr]
    await state.update_data(message_mode=mode)
    await callback.message.edit_reply_markup()  # type: ignore[union-attr]
    data = await state.get_data()
    is_window = data.get("interval_type") == "window"

    if mode == "exact":
        await state.set_state(ScheduleForm.waiting_for_messages)
        step = "4" if is_window else "5"
        await callback.message.answer(  # type: ignore[union-attr]
            f"Step {step} — <b>Enter your message(s)</b>\n\n"
            "Type one message — or multiple messages, one per line. "
            "Each send will pick one at random.\n\n"
            "<i>Maximum 20 messages, 4000 characters each.</i>",
            parse_mode="HTML",
        )
    else:
        await state.set_state(ScheduleForm.waiting_for_language)
        step = "4" if is_window else "5"
        await callback.message.answer(  # type: ignore[union-attr]
            f"Step {step} — <b>Language?</b>\n\nChoose the language for the generated messages:",
            reply_markup=language_keyboard(),
            parse_mode="HTML",
        )
    await callback.answer()


@router.message(ScheduleForm.waiting_for_messages)
async def process_messages(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not await _is_approved(message.from_user.id):
        return
    raw = (message.text or "").strip()
    msgs = [line.strip() for line in raw.splitlines() if line.strip()]
    if not msgs:
        await message.answer("Please enter at least one message.")
        return
    if len(msgs) > 20:
        await message.answer("Maximum 20 messages. Please trim your list.")
        return
    if any(len(m) > 4000 for m in msgs):
        await message.answer("Each message must be under 4000 characters.")
        return

    await state.update_data(messages=msgs)
    data = await state.get_data()
    await state.set_state(ScheduleForm.waiting_for_confirm)

    jitter = data.get("jitter_seconds")
    jitter_line = (
        f"• Randomization: {_jitter_label(jitter)}\n" if jitter else ""
    )
    preview = msgs[0][:120] + ("…" if len(msgs[0]) > 120 else "")
    count_line = f" ({len(msgs)} messages, random pick)" if len(msgs) > 1 else ""

    await message.answer(
        "📋 <b>Confirm your schedule:</b>\n\n"
        f"• Recipient: <code>{data['target']}</code>\n"
        f"• Frequency: {data['interval_label']}\n"
        f"{jitter_line}"
        f"• Mode: ✍️ Exact message{count_line}\n"
        f"• Preview: <i>{preview}</i>\n\n"
        f"Ready to activate?{_BOT_SEND_NOTICE}",
        reply_markup=confirm_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("lang:"), ScheduleForm.waiting_for_language)
async def process_language(callback: CallbackQuery, state: FSMContext) -> None:
    language = callback.data.split(":")[1]  # type: ignore[union-attr]
    await state.update_data(language=language)
    await callback.message.edit_reply_markup()  # type: ignore[union-attr]

    data = await state.get_data()
    # window: target(1) interval(2) mode(3) lang(4) → topic(5)
    # other:  target(1) interval(2) rand(3) mode(4) lang(5) → topic(6)
    step = "5" if data.get("interval_type") == "window" else "6"
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
        f"• Randomization: {_jitter_label(jitter)}\n" if jitter else ""
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

    uid = callback.from_user.id
    if not await _is_admin(uid):
        n = await count_user_tasks(uid)
        if n >= settings.max_schedules_per_user:
            await callback.message.answer(  # type: ignore[union-attr]
                f"❌ You've reached the limit of {settings.max_schedules_per_user} active "
                "schedules. Cancel or delete one before creating a new one."
            )
            await callback.answer()
            return

    data = await state.get_data()
    await state.clear()
    await callback.message.edit_reply_markup()  # type: ignore[union-attr]

    jitter: int | None = data.get("jitter_seconds")
    interval_label = data["interval_label"]
    if jitter:
        interval_label += f" ({_jitter_label(jitter)} randomization)"

    mode: str = data.get("message_mode", "ai")
    messages_json: str | None = None
    if mode == "exact":
        msgs: list[str] = data.get("messages", [])
        messages_json = json.dumps(msgs, ensure_ascii=False)
        topic = msgs[0][:100]
        language = "—"
    else:
        topic = data["topic"]
        language = data.get("language", "English")

    try:
        task = await create_task(
            user_telegram_id=uid,
            target_username=data["target"],
            topic=topic,
            interval_type=data["interval_type"],
            interval_value=data["interval_value"],
            interval_label=interval_label,
            jitter_seconds=jitter,
            language=language,
            message_mode=mode,
            messages_json=messages_json,
        )
        mode_label = "✍️ exact" if mode == "exact" else f"🤖 AI · {task.language}"
        await callback.message.answer(  # type: ignore[union-attr]
            f"✅ Schedule created! (ID: <code>{task.id}</code>)\n"
            f"Sending to {task.target_username} — {task.interval_label} — {mode_label}.",
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
    is_admin = await _is_admin(uid)
    tasks = await list_all_active_tasks() if is_admin else await list_active_tasks(uid)

    if not tasks:
        await message.answer("No active schedules. Use /schedule to create one.")
        return

    for task in tasks:
        last = task.last_sent_at.strftime("%Y-%m-%d %H:%M UTC") if task.last_sent_at else "never"
        nrt = get_next_run_time(task.job_id)
        next_run = "— (paused)" if task.is_paused else (
            nrt.strftime("%Y-%m-%d %H:%M UTC") if nrt else "—"
        )
        header = "⏸" if task.is_paused else "🗓"
        paused_suffix = " <i>(paused)</i>" if task.is_paused else ""
        owner_line = (
            f"• Owner: <code>{task.user_telegram_id or 'unknown (legacy)'}</code>\n"
            if is_admin
            else ""
        )
        failure_line = (
            f"• ⚠️ Failures: {task.consecutive_failures} consecutive\n"
            if task.consecutive_failures > 0
            else ""
        )
        if task.message_mode == "exact":
            mode_line = "• Mode: ✍️ Exact message\n"
            content_line = f"• Preview: <i>{task.topic[:80]}</i>\n"
        else:
            mode_line = f"• Language: {task.language}\n"
            content_line = f"• Topic: <i>{task.topic}</i>\n"
        text = (
            f"{header} <b>Schedule #{task.id}</b>{paused_suffix}\n"
            f"{owner_line}"
            f"• To: <code>{task.target_username}</code>\n"
            f"• Frequency: {task.interval_label}\n"
            f"{mode_line}"
            f"{content_line}"
            f"• Last sent: {last}\n"
            f"• Next run: {next_run}\n"
            f"{failure_line}"
        )
        await message.answer(
            text.rstrip(), reply_markup=task_keyboard(task.id, task.is_paused), parse_mode="HTML"
        )


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
    is_admin = await _is_admin(uid)
    success = await cancel_task(task_id, uid, force=is_admin)
    await callback.message.edit_reply_markup()  # type: ignore[union-attr]
    if success:
        await callback.message.answer(f"🗑 Schedule #{task_id} cancelled.")  # type: ignore[union-attr]
    else:
        await callback.message.answer(f"Schedule #{task_id} not found.")  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(F.data.startswith("pause_task:"))
async def pause_task_callback(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        return
    task_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    uid = callback.from_user.id
    is_admin = await _is_admin(uid)
    success = await pause_task(task_id, uid, force=is_admin)
    await callback.message.edit_reply_markup()  # type: ignore[union-attr]
    if success:
        await callback.message.answer(  # type: ignore[union-attr]
            f"⏸ Schedule #{task_id} paused. Use /list to resume it."
        )
    else:
        await callback.message.answer(  # type: ignore[union-attr]
            f"Schedule #{task_id} not found or already paused."
        )
    await callback.answer()


@router.callback_query(F.data.startswith("resume_task:"))
async def resume_task_callback(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        return
    task_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    uid = callback.from_user.id
    is_admin = await _is_admin(uid)
    success = await resume_task(task_id, uid, force=is_admin)
    await callback.message.edit_reply_markup()  # type: ignore[union-attr]
    if success:
        await callback.message.answer(  # type: ignore[union-attr]
            f"▶ Schedule #{task_id} resumed."
        )
    else:
        await callback.message.answer(  # type: ignore[union-attr]
            f"Schedule #{task_id} not found or not paused."
        )
    await callback.answer()


@router.callback_query(F.data.startswith("send_now:"))
async def send_now_callback(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        return
    task_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    uid = callback.from_user.id
    is_admin = await _is_admin(uid)

    if not is_admin and not await _is_approved(uid):
        await callback.answer("Access denied.", show_alert=True)
        return

    await callback.answer("Generating…")
    try:
        text = await fire_task_now(task_id)
        await callback.message.answer(  # type: ignore[union-attr]
            f"✅ <b>Sent (Schedule #{task_id}):</b>\n\n{text}",
            parse_mode="HTML",
        )
    except ValueError as exc:
        await callback.message.answer(f"❌ {exc}", parse_mode="HTML")  # type: ignore[union-attr]
    except Exception as exc:
        logger.exception("Manual send failed for task %d", task_id)
        await callback.message.answer(  # type: ignore[union-attr]
            f"❌ <b>Send failed:</b> <i>{exc}</i>", parse_mode="HTML"
        )


# ── History & Edit ────────────────────────────────────────────────────────────


@router.callback_query(F.data.startswith("history:"))
async def cb_history(callback: CallbackQuery) -> None:
    task_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    entries = await get_task_history(task_id, limit=10)
    if not entries:
        await callback.answer("No history yet.", show_alert=True)
        return
    lines = [f"📋 <b>Last {len(entries)} messages for Schedule #{task_id}:</b>"]
    for e in entries:
        sent = e.sent_at.strftime("%m-%d %H:%M UTC")
        lines.append(f"\n<i>{sent}</i>\n{e.content}")
    await callback.message.answer("\n".join(lines), parse_mode="HTML")  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(F.data.startswith("edit_task:"))
async def cb_edit_task(callback: CallbackQuery) -> None:
    task_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    task = await get_task(task_id)
    mode = task.message_mode if task else "ai"
    await callback.message.answer(  # type: ignore[union-attr]
        f"✏️ <b>Edit Schedule #{task_id}</b>\n\nWhat would you like to change?",
        reply_markup=edit_field_keyboard(task_id, mode),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("edit_topic:"))
async def cb_edit_topic(callback: CallbackQuery, state: FSMContext) -> None:
    task_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    await state.update_data(edit_task_id=task_id)
    await state.set_state(EditForm.waiting_for_topic)
    await callback.message.edit_reply_markup()  # type: ignore[union-attr]
    await callback.message.answer("📝 Enter the new topic for this schedule:")  # type: ignore[union-attr]
    await callback.answer()


@router.message(EditForm.waiting_for_topic)
async def process_edit_topic(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not await _is_approved(message.from_user.id):
        return
    topic = (message.text or "").strip()
    if len(topic) < 3:
        await message.answer("Please provide a more descriptive topic.")
        return
    data = await state.get_data()
    task_id: int = data["edit_task_id"]
    uid = message.from_user.id
    ok = await update_task_topic(task_id, uid, topic, force=await _is_admin(uid))
    await state.clear()
    if ok:
        await message.answer(f"✅ Topic updated for Schedule #{task_id}.")
    else:
        await message.answer(f"❌ Could not update Schedule #{task_id}.")


@router.callback_query(F.data.startswith("edit_lang:"))
async def cb_edit_lang(callback: CallbackQuery) -> None:
    task_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    await callback.message.edit_reply_markup()  # type: ignore[union-attr]
    await callback.message.answer(  # type: ignore[union-attr]
        "🌐 Choose the new language:",
        reply_markup=edit_language_keyboard(task_id),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("edit_lang_val:"))
async def cb_edit_lang_val(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        return
    parts = (callback.data or "").split(":")

    task_id = int(parts[1])
    language = parts[2]
    uid = callback.from_user.id
    ok = await update_task_language(task_id, uid, language, force=await _is_admin(uid))
    await callback.message.edit_reply_markup()  # type: ignore[union-attr]
    if ok:
        await callback.message.answer(  # type: ignore[union-attr]
            f"✅ Language updated to <b>{language}</b> for Schedule #{task_id}.", parse_mode="HTML"
        )
    else:
        await callback.message.answer(f"❌ Could not update Schedule #{task_id}.")  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(F.data.startswith("edit_freq:"))
async def cb_edit_freq(callback: CallbackQuery, state: FSMContext) -> None:
    task_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    await state.update_data(edit_task_id=task_id)
    await state.set_state(EditForm.waiting_for_interval)
    await callback.message.edit_reply_markup()  # type: ignore[union-attr]
    await callback.message.answer(  # type: ignore[union-attr]
        "⏱ Enter the new frequency:\n\n"
        "• <code>30m</code> — every 30 minutes\n"
        "• <code>2h</code> — every 2 hours\n"
        "• <code>1d</code> — every day\n"
        "• <code>daily 09:00</code> — every day at 09:00 UTC\n"
        "• <code>window 15:15-15:50</code> — daily at a random time in that range",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(EditForm.waiting_for_interval)
async def process_edit_interval(message: Message, state: FSMContext) -> None:
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
    data = await state.get_data()
    task_id: int = data["edit_task_id"]
    uid = message.from_user.id
    ok = await update_task_interval(
        task_id, uid, interval_type, interval_value, interval_label,
        force=await _is_admin(uid),
    )
    await state.clear()
    if ok:
        await message.answer(
            f"✅ Frequency updated to <b>{interval_label}</b> for Schedule #{task_id}.",
            parse_mode="HTML",
        )
    else:
        await message.answer(f"❌ Could not update Schedule #{task_id}.")


@router.callback_query(F.data.startswith("edit_messages:"))
async def cb_edit_messages(callback: CallbackQuery, state: FSMContext) -> None:
    task_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    await state.update_data(edit_task_id=task_id)
    await state.set_state(EditForm.waiting_for_messages)
    await callback.message.edit_reply_markup()  # type: ignore[union-attr]
    await callback.message.answer(  # type: ignore[union-attr]
        "📝 Enter the new message(s), one per line.\n"
        "Multiple messages = one picked randomly each send.\n\n"
        "<i>Maximum 20 messages, 4000 characters each.</i>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(EditForm.waiting_for_messages)
async def process_edit_messages(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not await _is_approved(message.from_user.id):
        return
    raw = (message.text or "").strip()
    msgs = [line.strip() for line in raw.splitlines() if line.strip()]
    if not msgs:
        await message.answer("Please enter at least one message.")
        return
    if len(msgs) > 20:
        await message.answer("Maximum 20 messages. Please trim your list.")
        return
    if any(len(m) > 4000 for m in msgs):
        await message.answer("Each message must be under 4000 characters.")
        return
    data = await state.get_data()
    task_id: int = data["edit_task_id"]
    uid = message.from_user.id
    ok = await update_task_messages(
        task_id, uid, json.dumps(msgs, ensure_ascii=False), force=await _is_admin(uid)
    )
    await state.clear()
    if ok:
        count_label = f"{len(msgs)} messages" if len(msgs) > 1 else "message"
        await message.answer(f"✅ Updated {count_label} for Schedule #{task_id}.")
    else:
        await message.answer(f"❌ Could not update Schedule #{task_id}.")
