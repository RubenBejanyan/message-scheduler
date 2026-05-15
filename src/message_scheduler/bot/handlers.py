import json
import logging

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    Message,
    MessageOriginChannel,
    MessageOriginChat,
    MessageOriginUser,
)

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
    preview_task,
    resume_task,
    update_task_interval,
    update_task_language,
    update_task_messages,
    update_task_target,
    update_task_timezone,
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
    edit_timezone_keyboard,
    language_keyboard,
    message_mode_keyboard,
    nav_keyboard,
    randomization_keyboard,
    repeat_count_keyboard,
    task_keyboard,
    timezone_keyboard,
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


@router.message(Command("id"))
async def cmd_id(message: Message) -> None:
    """Reply with the current chat's ID — useful for finding a group's numeric ID."""
    chat = message.chat
    display = chat.title or chat.username or str(chat.id)
    await message.answer(
        f"Chat ID: <code>{chat.id}</code>\n"
        f"Name: <b>{display}</b>\n"
        f"Type: {chat.type}",
        parse_mode="HTML",
    )


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


# ── Target accessibility check ────────────────────────────────────────────────


async def _check_target_accessible(bot: Bot, target: str) -> str | None:
    """Return None if the bot can message this target, or a human-readable error."""
    chat_id: int | str = int(target) if target.lstrip("-").isdigit() else target
    try:
        await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        return None
    except TelegramForbiddenError:
        # Try to get chat info for a more specific error message
        try:
            chat = await bot.get_chat(chat_id)
            if chat.type in ("group", "supergroup", "channel"):
                return (
                    f"The bot is not a member of <b>{chat.title}</b>.\n"
                    "Add the bot to the group/channel first, then try again."
                )
            name = chat.full_name or str(chat.id)
            return (
                f"<b>{name}</b> hasn't started a conversation with this bot.\n"
                "They need to send /start to the bot first."
            )
        except Exception:
            pass
        if isinstance(chat_id, int) and chat_id < 0:
            return (
                "The bot is not a member of that group/channel.\n"
                "Add the bot first, then try again."
            )
        return (
            f"Cannot send to <code>{target}</code>.\n"
            "If it's a user, they need to send /start to this bot first."
        )
    except TelegramBadRequest:
        return (
            f"Could not find <code>{target}</code>.\n"
            "Check the username or ID is correct."
        )
    except Exception:
        return None  # Transient error — don't block the user


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
        "Choose one of:\n"
        "• <code>@username</code> — user or public group/channel\n"
        "• <code>-100XXXXXXXXXX</code> — group without a @username\n"
        "• <b>Forward any message</b> from the target user or channel\n\n"
        "<i>For groups without a @username: add the bot and send "
        "<code>/id</code> there to get the numeric ID.</i>",
        reply_markup=nav_keyboard(show_back=False),
        parse_mode="HTML",
    )


def _extract_forward_target(message: Message) -> tuple[int, str] | None:
    """Return (id, display_name) from a forwarded message — user, group, or channel."""
    # Legacy fields (still sent by most clients alongside forward_origin)
    if message.forward_from_chat and message.forward_from_chat.id:
        c = message.forward_from_chat
        return c.id, c.title or c.username or str(c.id)
    if message.forward_from and message.forward_from.id:
        u = message.forward_from
        return u.id, u.full_name or u.username or str(u.id)
    # Modern forward_origin (Bot API 7.0+)
    origin = message.forward_origin
    if isinstance(origin, MessageOriginChannel):
        return origin.chat.id, origin.chat.title or origin.chat.username or str(origin.chat.id)
    if isinstance(origin, MessageOriginChat):
        c = origin.sender_chat
        return c.id, c.title or str(c.id)
    if isinstance(origin, MessageOriginUser):
        u = origin.sender_user
        return u.id, u.full_name or u.username or str(u.id)
    # MessageOriginHiddenUser — privacy settings hide the sender's identity
    return None


@router.message(
    ScheduleForm.waiting_for_target,
    F.forward_from_chat | F.forward_from | F.forward_origin,
)
async def process_target_forward(message: Message, state: FSMContext, bot: Bot) -> None:
    """Handle a forwarded message in step 1 — auto-detect user/group/channel ID."""
    if message.from_user is None or not await _is_approved(message.from_user.id):
        return
    result = _extract_forward_target(message)
    if result is None:
        await message.answer(
            "Could not read the sender's ID — they have privacy settings enabled.\n\n"
            "Ask them to send their ID directly, or use <code>/id</code> "
            "inside the target group.",
            reply_markup=nav_keyboard(show_back=False),
            parse_mode="HTML",
        )
        return
    chat_id, display = result
    target = str(chat_id)
    warning = await _check_target_accessible(bot, target)
    warning_line = (
        f"\n\n⚠️ <i>{warning}\nMake sure access is granted before the first send.</i>"
        if warning else ""
    )
    await state.update_data(target=target)
    await state.set_state(ScheduleForm.waiting_for_interval)
    await message.answer(
        f"✅ Detected: <b>{display}</b> (<code>{target}</code>){warning_line}\n\n"
        "Step 2 — <b>How often / when should I send?</b>\n\n"
        "• <code>30m</code> — every 30 minutes\n"
        "• <code>2h</code> — every 2 hours\n"
        "• <code>1d</code> — every day\n"
        "• <code>daily 09:00</code> — every day at 09:00 UTC\n"
        "• <code>window 15:15-15:50</code> — daily at a random time in that range",
        reply_markup=nav_keyboard(),
        parse_mode="HTML",
    )


@router.message(ScheduleForm.waiting_for_target)
async def process_target(message: Message, state: FSMContext, bot: Bot) -> None:
    if message.from_user is None or not await _is_approved(message.from_user.id):
        return
    text = (message.text or "").strip()
    is_username = text.startswith("@") and len(text) >= 2
    is_numeric = len(text) > 1 and text.lstrip("-").isdigit()
    if not is_username and not is_numeric:
        await message.answer(
            "Please enter a valid <code>@username</code>, numeric chat ID "
            "(e.g. <code>-100123456789</code>), or forward any message from the target.",
            parse_mode="HTML",
        )
        return
    warning = await _check_target_accessible(bot, text)
    warning_line = (
        f"\n\n⚠️ <i>{warning}\nMake sure access is granted before the first send.</i>"
        if warning else ""
    )
    await state.update_data(target=text)
    await state.set_state(ScheduleForm.waiting_for_interval)
    await message.answer(
        f"Step 2 — <b>How often / when should I send?</b>{warning_line}\n\n"
        "• <code>30m</code> — every 30 minutes\n"
        "• <code>2h</code> — every 2 hours\n"
        "• <code>1d</code> — every day\n"
        "• <code>daily 09:00</code> — every day at 09:00 UTC\n"
        "• <code>window 15:15-15:50</code> — daily at a random time in that range",
        reply_markup=nav_keyboard(),
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
            f"Could not parse that. Try:\n{_INTERVAL_PROMPT}",
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

    if interval_type == "interval":
        # Relative intervals are timezone-agnostic — skip timezone step.
        await state.update_data(timezone="UTC")
        await state.set_state(ScheduleForm.waiting_for_randomization)
        await message.answer(
            "Step 3 — <b>Randomization</b>\n\n"
            "Add a random delay so messages don't always arrive at the exact same time.\n\n"
            "Pick a preset or type a custom amount (e.g. <code>45m</code>, <code>3h</code>, "
            "<code>90</code> for 90 minutes):",
            reply_markup=randomization_keyboard(),
            parse_mode="HTML",
        )
    else:
        # cron/window/once fire at a specific local time — ask for timezone first.
        if interval_type in ("window", "once"):
            await state.update_data(jitter_seconds=None)
        await state.set_state(ScheduleForm.waiting_for_timezone)
        await message.answer(
            "Step 3 — <b>Timezone</b>\n\nWhat timezone should the schedule use?",
            reply_markup=timezone_keyboard(),
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("tz:"), ScheduleForm.waiting_for_timezone)
async def process_timezone(callback: CallbackQuery, state: FSMContext) -> None:
    tz = (callback.data or "").split(":")[1]
    await state.update_data(timezone=tz)
    data = await state.get_data()
    await callback.message.edit_reply_markup()  # type: ignore[union-attr]

    interval_type = data.get("interval_type")
    if interval_type == "once":
        await state.set_state(ScheduleForm.waiting_for_mode)
        await callback.message.answer(  # type: ignore[union-attr]
            "Step 4 — <b>What should I send?</b>",
            reply_markup=message_mode_keyboard(),
            parse_mode="HTML",
        )
    elif interval_type == "window":
        await state.set_state(ScheduleForm.waiting_for_repeat_count)
        await callback.message.answer(  # type: ignore[union-attr]
            "Step 4 — <b>How many times?</b>\n\n"
            "Choose how many times this message should be sent, "
            "or pick <b>Unlimited</b> for no cap.\n\n"
            "You can also type a custom number (e.g. <code>15</code>):",
            reply_markup=repeat_count_keyboard(),
            parse_mode="HTML",
        )
    else:  # cron
        await state.set_state(ScheduleForm.waiting_for_randomization)
        await callback.message.answer(  # type: ignore[union-attr]
            "Step 4 — <b>Randomization</b>\n\n"
            "Add a random delay so messages don't always arrive at the exact same time.\n\n"
            "Pick a preset or type a custom amount (e.g. <code>45m</code>, <code>3h</code>, "
            "<code>90</code> for 90 minutes):",
            reply_markup=randomization_keyboard(),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data.startswith("jitter:"), ScheduleForm.waiting_for_randomization)
async def process_randomization(callback: CallbackQuery, state: FSMContext) -> None:
    raw = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    jitter = raw if raw > 0 else None
    await state.update_data(jitter_seconds=jitter)
    data = await state.get_data()
    step = "5" if data.get("interval_type") == "cron" else "4"
    await callback.message.edit_reply_markup()  # type: ignore[union-attr]
    await state.set_state(ScheduleForm.waiting_for_repeat_count)
    await callback.message.answer(  # type: ignore[union-attr]
        f"Step {step} — <b>How many times?</b>\n\n"
        "Choose how many times this message should be sent, "
        "or pick <b>Unlimited</b> for no cap.\n\n"
        "You can also type a custom number (e.g. <code>15</code>):",
        reply_markup=repeat_count_keyboard(),
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
    data = await state.get_data()
    step = "5" if data.get("interval_type") == "cron" else "4"
    await state.set_state(ScheduleForm.waiting_for_repeat_count)
    await message.answer(
        f"Step {step} — <b>How many times?</b>\n\n"
        "Choose how many times this message should be sent, "
        "or pick <b>Unlimited</b> for no cap.\n\n"
        "You can also type a custom number (e.g. <code>15</code>):",
        reply_markup=repeat_count_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("repeat:"), ScheduleForm.waiting_for_repeat_count)
async def process_repeat_count(callback: CallbackQuery, state: FSMContext) -> None:
    raw = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    repeat_count: int | None = raw if raw > 0 else None
    await state.update_data(repeat_count=repeat_count)
    data = await state.get_data()
    interval_type = data.get("interval_type", "interval")
    step = "6" if interval_type == "cron" else "5"
    await callback.message.edit_reply_markup()  # type: ignore[union-attr]
    await state.set_state(ScheduleForm.waiting_for_mode)
    await callback.message.answer(  # type: ignore[union-attr]
        f"Step {step} — <b>What should I send?</b>",
        reply_markup=message_mode_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(ScheduleForm.waiting_for_repeat_count)
async def process_repeat_count_text(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not await _is_approved(message.from_user.id):
        return
    raw = (message.text or "").strip()
    if raw.lower() in ("0", "unlimited", "none", "no", "∞"):
        repeat_count: int | None = None
    else:
        try:
            n = int(raw)
            if n <= 0:
                raise ValueError
            repeat_count = n
        except ValueError:
            await message.answer(
                "Please enter a positive number (e.g. <code>10</code>), "
                "or press <b>♾ Unlimited</b>.",
                parse_mode="HTML",
            )
            return
    await state.update_data(repeat_count=repeat_count)
    data = await state.get_data()
    interval_type = data.get("interval_type", "interval")
    step = "6" if interval_type == "cron" else "5"
    await state.set_state(ScheduleForm.waiting_for_mode)
    await message.answer(
        f"Step {step} — <b>What should I send?</b>",
        reply_markup=message_mode_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("mode:"), ScheduleForm.waiting_for_mode)
async def process_mode(callback: CallbackQuery, state: FSMContext) -> None:
    mode = callback.data.split(":")[1]  # type: ignore[union-attr]
    await state.update_data(message_mode=mode)
    await callback.message.edit_reply_markup()  # type: ignore[union-attr]
    data = await state.get_data()
    interval_type = data.get("interval_type", "interval")
    # cron: mode(6)→content(7); once: mode(4)→content(5); interval/window: mode(5)→content(6)
    if interval_type == "cron":
        step = "7"
    elif interval_type == "once":
        step = "5"
    else:
        step = "6"

    if mode == "exact":
        await state.set_state(ScheduleForm.waiting_for_messages)
        await callback.message.answer(  # type: ignore[union-attr]
            f"Step {step} — <b>Enter your message(s)</b>\n\n"
            "Type one message — or multiple messages, one per line. "
            "Each send will pick one at random.\n\n"
            "<i>Maximum 20 messages, 4000 characters each.</i>",
            parse_mode="HTML",
        )
    else:
        await state.set_state(ScheduleForm.waiting_for_language)
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

    interval_type = data.get("interval_type", "interval")
    jitter = data.get("jitter_seconds")
    jitter_line = f"• Randomization: {_jitter_label(jitter)}\n" if jitter else ""
    tz = data.get("timezone", "UTC")
    tz_line = f"• Timezone: {tz}\n" if interval_type != "interval" else ""
    schedule_key = "Send time" if interval_type == "once" else "Frequency"
    repeat_count = data.get("repeat_count")
    repeat_line = f"• Repeat: {repeat_count} times\n" if repeat_count else ""
    preview = msgs[0][:120] + ("…" if len(msgs[0]) > 120 else "")
    count_line = f" ({len(msgs)} messages, random pick)" if len(msgs) > 1 else ""

    await message.answer(
        "📋 <b>Confirm your schedule:</b>\n\n"
        f"• Recipient: <code>{data['target']}</code>\n"
        f"• {schedule_key}: {data['interval_label']}\n"
        f"{tz_line}"
        f"{jitter_line}"
        f"{repeat_line}"
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
    # cron: lang(7)→topic(8); once: lang(5)→topic(6); interval/window: lang(6)→topic(7)
    interval_type = data.get("interval_type", "interval")
    if interval_type == "cron":
        step = "8"
    elif interval_type == "once":
        step = "6"
    else:
        step = "7"
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

    interval_type = data.get("interval_type", "interval")
    jitter = data.get("jitter_seconds")
    jitter_line = f"• Randomization: {_jitter_label(jitter)}\n" if jitter else ""
    tz = data.get("timezone", "UTC")
    tz_line = f"• Timezone: {tz}\n" if interval_type != "interval" else ""
    schedule_key = "Send time" if interval_type == "once" else "Frequency"
    repeat_count = data.get("repeat_count")
    repeat_line = f"• Repeat: {repeat_count} times\n" if repeat_count else ""

    await message.answer(
        "📋 <b>Confirm your schedule:</b>\n\n"
        f"• Recipient: <code>{data['target']}</code>\n"
        f"• {schedule_key}: {data['interval_label']}\n"
        f"{tz_line}"
        f"{jitter_line}"
        f"{repeat_line}"
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
    repeat_count: int | None = data.get("repeat_count")
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
            timezone=data.get("timezone", "UTC"),
            repeat_count=repeat_count,
        )
        mode_label = "✍️ exact" if mode == "exact" else f"🤖 AI · {task.language}"
        repeat_suffix = f" · up to {repeat_count}×" if repeat_count else ""
        await callback.message.answer(  # type: ignore[union-attr]
            f"✅ Schedule created! (ID: <code>{task.id}</code>)\n"
            f"Sending to {task.target_username} — {task.interval_label}"
            f"{repeat_suffix} — {mode_label}.",
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


@router.callback_query(F.data == "wizard_cancel")
async def wizard_cancel_callback(callback: CallbackQuery, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state and current_state.startswith("ScheduleForm:"):
        await state.clear()
        await callback.message.edit_reply_markup()  # type: ignore[union-attr]
        await callback.message.answer("❌ Scheduling cancelled. Use /schedule to start again.")  # type: ignore[union-attr]
    await callback.answer()


_INTERVAL_PROMPT = (
    "• <code>30m</code> — every 30 minutes\n"
    "• <code>2h</code> — every 2 hours\n"
    "• <code>1d</code> — every day\n"
    "• <code>daily 09:00</code> — every day at 09:00 UTC\n"
    "• <code>window 15:15-15:50</code> — daily at a random time in that range\n"
    "• <code>once 2026-05-20 14:30</code> — send once on that date and time"
)


@router.callback_query(F.data == "wizard_back")
async def wizard_back_callback(callback: CallbackQuery, state: FSMContext) -> None:
    current_state = await state.get_state()
    if not current_state or not current_state.startswith("ScheduleForm:"):
        await callback.answer("No active scheduling wizard.", show_alert=True)
        return

    data = await state.get_data()
    interval_type: str = data.get("interval_type", "interval")
    message_mode: str = data.get("message_mode", "ai")

    await callback.message.edit_reply_markup()  # type: ignore[union-attr]

    if current_state == ScheduleForm.waiting_for_interval.state:
        await state.set_state(ScheduleForm.waiting_for_target)
        await callback.message.answer(  # type: ignore[union-attr]
            "Step 1 — <b>Who should receive the messages?</b>\n\n"
            "Choose one of:\n"
            "• Type <code>@username</code> — user or public group/channel\n"
            "• Type <code>-100XXXXXXXXXX</code> — group without a @username (numeric chat ID)\n"
            "• <b>Forward any message</b> from the target group — the bot detects it automatically",
            reply_markup=nav_keyboard(show_back=False),
            parse_mode="HTML",
        )

    elif current_state == ScheduleForm.waiting_for_timezone.state:
        await state.set_state(ScheduleForm.waiting_for_interval)
        await callback.message.answer(  # type: ignore[union-attr]
            f"Step 2 — <b>How often / when should I send?</b>\n\n{_INTERVAL_PROMPT}",
            reply_markup=nav_keyboard(),
            parse_mode="HTML",
        )

    elif current_state == ScheduleForm.waiting_for_randomization.state:
        if interval_type == "cron":
            await state.set_state(ScheduleForm.waiting_for_timezone)
            await callback.message.answer(  # type: ignore[union-attr]
                "Step 3 — <b>Timezone</b>\n\nWhat timezone should the schedule use?",
                reply_markup=timezone_keyboard(),
                parse_mode="HTML",
            )
        else:
            await state.set_state(ScheduleForm.waiting_for_interval)
            await callback.message.answer(  # type: ignore[union-attr]
                f"Step 2 — <b>How often / when should I send?</b>\n\n{_INTERVAL_PROMPT}",
                reply_markup=nav_keyboard(),
                parse_mode="HTML",
            )

    elif current_state == ScheduleForm.waiting_for_repeat_count.state:
        if interval_type == "window":
            await state.set_state(ScheduleForm.waiting_for_timezone)
            await callback.message.answer(  # type: ignore[union-attr]
                "Step 3 — <b>Timezone</b>\n\nWhat timezone should the schedule use?",
                reply_markup=timezone_keyboard(),
                parse_mode="HTML",
            )
        else:  # interval or cron
            step = "4" if interval_type == "cron" else "3"
            await state.set_state(ScheduleForm.waiting_for_randomization)
            await callback.message.answer(  # type: ignore[union-attr]
                f"Step {step} — <b>Randomization</b>\n\n"
                "Add a random delay so messages don't always arrive at the exact same time.\n\n"
                "Pick a preset or type a custom amount (e.g. <code>45m</code>, <code>3h</code>, "
                "<code>90</code> for 90 minutes):",
                reply_markup=randomization_keyboard(),
                parse_mode="HTML",
            )

    elif current_state == ScheduleForm.waiting_for_mode.state:
        if interval_type == "once":
            await state.set_state(ScheduleForm.waiting_for_timezone)
            await callback.message.answer(  # type: ignore[union-attr]
                "Step 3 — <b>Timezone</b>\n\nWhat timezone should the schedule use?",
                reply_markup=timezone_keyboard(),
                parse_mode="HTML",
            )
        else:
            step = "5" if interval_type == "cron" else "4"
            await state.set_state(ScheduleForm.waiting_for_repeat_count)
            await callback.message.answer(  # type: ignore[union-attr]
                f"Step {step} — <b>How many times?</b>\n\n"
                "Choose how many times this message should be sent, "
                "or pick <b>Unlimited</b> for no cap.\n\n"
                "You can also type a custom number (e.g. <code>15</code>):",
                reply_markup=repeat_count_keyboard(),
                parse_mode="HTML",
            )

    elif current_state == ScheduleForm.waiting_for_language.state:
        if interval_type == "cron":
            step = "6"
        elif interval_type == "once":
            step = "4"
        else:
            step = "5"
        await state.set_state(ScheduleForm.waiting_for_mode)
        await callback.message.answer(  # type: ignore[union-attr]
            f"Step {step} — <b>What should I send?</b>",
            reply_markup=message_mode_keyboard(),
            parse_mode="HTML",
        )

    elif current_state == ScheduleForm.waiting_for_topic.state:
        if interval_type == "cron":
            step = "7"
        elif interval_type == "once":
            step = "5"
        else:
            step = "6"
        await state.set_state(ScheduleForm.waiting_for_language)
        await callback.message.answer(  # type: ignore[union-attr]
            f"Step {step} — <b>Language?</b>\n\nChoose the language for the generated messages:",
            reply_markup=language_keyboard(),
            parse_mode="HTML",
        )

    elif current_state == ScheduleForm.waiting_for_messages.state:
        if interval_type == "cron":
            step = "6"
        elif interval_type == "once":
            step = "4"
        else:
            step = "5"
        await state.set_state(ScheduleForm.waiting_for_mode)
        await callback.message.answer(  # type: ignore[union-attr]
            f"Step {step} — <b>What should I send?</b>",
            reply_markup=message_mode_keyboard(),
            parse_mode="HTML",
        )

    elif current_state == ScheduleForm.waiting_for_confirm.state:
        if message_mode == "exact":
            if interval_type == "cron":
                step = "7"
            elif interval_type == "once":
                step = "5"
            else:
                step = "6"
            await state.set_state(ScheduleForm.waiting_for_messages)
            await callback.message.answer(  # type: ignore[union-attr]
                f"Step {step} — <b>Enter your message(s)</b>\n\n"
                "Type one message — or multiple messages, one per line. "
                "Each send will pick one at random.\n\n"
                "<i>Maximum 20 messages, 4000 characters each.</i>",
                reply_markup=nav_keyboard(),
                parse_mode="HTML",
            )
        else:
            if interval_type == "cron":
                step = "8"
            elif interval_type == "once":
                step = "6"
            else:
                step = "7"
            await state.set_state(ScheduleForm.waiting_for_topic)
            await callback.message.answer(  # type: ignore[union-attr]
                f"Step {step} — <b>What should the messages be about?</b>\n\n"
                "Describe the topic or context (e.g. <i>good morning motivation</i>, "
                "<i>remind her to drink water</i>):",
                reply_markup=nav_keyboard(),
                parse_mode="HTML",
            )

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
        tz_line = (
            f"• Timezone: {task.timezone}\n" if task.interval_type != "interval" else ""
        )
        progress_line = (
            f"• Progress: {task.sent_count} / {task.repeat_count} sent\n"
            if task.repeat_count
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
            f"{tz_line}"
            f"{progress_line}"
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
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return
    if not await _is_approved(message.from_user.id):
        return
    current_state = await state.get_state()
    if current_state and current_state.startswith("ScheduleForm:"):
        await state.clear()
        await message.answer("❌ Scheduling cancelled. Use /schedule to start again.")
    else:
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
    interval_type = task.interval_type if task else "interval"
    await callback.message.answer(  # type: ignore[union-attr]
        f"✏️ <b>Edit Schedule #{task_id}</b>\n\nWhat would you like to change?",
        reply_markup=edit_field_keyboard(task_id, mode, interval_type),
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
            f"Could not parse that. Try:\n{_INTERVAL_PROMPT}",
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


@router.callback_query(F.data.startswith("edit_target:"))
async def cb_edit_target(callback: CallbackQuery, state: FSMContext) -> None:
    task_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    await state.update_data(edit_task_id=task_id)
    await state.set_state(EditForm.waiting_for_target)
    await callback.message.edit_reply_markup()  # type: ignore[union-attr]
    await callback.message.answer(  # type: ignore[union-attr]
        "📮 Enter the new recipient @username or @group handle:"
    )
    await callback.answer()


@router.message(EditForm.waiting_for_target)
async def process_edit_target(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not await _is_approved(message.from_user.id):
        return
    text = (message.text or "").strip()
    if not text.startswith("@") or len(text) < 2:
        await message.answer("Please enter a valid @username or @group handle.")
        return
    data = await state.get_data()
    task_id: int = data["edit_task_id"]
    uid = message.from_user.id
    ok = await update_task_target(task_id, uid, text, force=await _is_admin(uid))
    await state.clear()
    if ok:
        await message.answer(
            f"✅ Recipient updated to <code>{text}</code> for Schedule #{task_id}.",
            parse_mode="HTML",
        )
    else:
        await message.answer(f"❌ Could not update Schedule #{task_id}.")


@router.callback_query(F.data.startswith("edit_tz:"))
async def cb_edit_tz(callback: CallbackQuery) -> None:
    task_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    await callback.message.edit_reply_markup()  # type: ignore[union-attr]
    await callback.message.answer(  # type: ignore[union-attr]
        "🕐 Choose the new timezone:",
        reply_markup=edit_timezone_keyboard(task_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("edit_tz_val:"))
async def cb_edit_tz_val(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        return
    parts = (callback.data or "").split(":")
    task_id = int(parts[1])
    tz = parts[2]
    uid = callback.from_user.id
    ok = await update_task_timezone(task_id, uid, tz, force=await _is_admin(uid))
    await callback.message.edit_reply_markup()  # type: ignore[union-attr]
    if ok:
        await callback.message.answer(  # type: ignore[union-attr]
            f"✅ Timezone updated to <b>{tz}</b> for Schedule #{task_id}.", parse_mode="HTML"
        )
    else:
        await callback.message.answer(f"❌ Could not update Schedule #{task_id}.")  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(F.data.startswith("preview:"))
async def cb_preview(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        return
    task_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    await callback.answer("Generating…")
    try:
        text = await preview_task(task_id)
        await callback.message.answer(  # type: ignore[union-attr]
            f"🔍 <b>Preview (Schedule #{task_id}):</b>\n\n{text}",
            parse_mode="HTML",
        )
    except ValueError as exc:
        await callback.message.answer(f"❌ {exc}")  # type: ignore[union-attr]
    except Exception as exc:
        logger.exception("Preview failed for task %d", task_id)
        await callback.message.answer(  # type: ignore[union-attr]
            f"❌ <b>Preview failed:</b> <i>{exc}</i>", parse_mode="HTML"
        )
