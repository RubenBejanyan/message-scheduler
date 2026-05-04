import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ..config import settings
from ..scheduler import cancel_task, create_task, list_active_tasks, parse_interval
from ..telegram_client import (
    complete_user_2fa,
    complete_user_code,
    disconnect_user,
    is_user_connected,
    start_user_auth,
)
from ..users import (
    block_user,
    get_user,
    list_active_users,
    list_blocked_users,
    register_user,
    set_session_status,
    unblock_user,
)
from .keyboards import (
    block_keyboard,
    cancel_task_keyboard,
    confirm_keyboard,
    connect_confirm_keyboard,
    language_keyboard,
    randomization_keyboard,
    send_as_keyboard,
    unblock_keyboard,
)
from .states import ScheduleForm, TelethonAuth

logger = logging.getLogger(__name__)
router = Router()

_JITTER_LABELS: dict[int, str] = {
    900: "±15 min",
    3600: "±1 hour",
    7200: "±2 hours",
}

_BOT_SEND_NOTICE = (
    "ℹ️ <b>Bot sending limitation:</b> the recipient must have previously "
    "started a conversation with this bot, or it must be a group/channel "
    "where the bot is a member."
)

_CONNECT_WARNING = (
    "⚠️ <b>Security notice</b>\n\n"
    "Connecting your account stores your Telegram session on this server. "
    "This allows the bot to send messages from your personal account.\n\n"
    "• Anyone with server access could use your session\n"
    "• You can revoke it anytime: "
    "<b>Telegram → Settings → Privacy and Security → Active Sessions</b>\n"
    "• The bot will <i>only</i> use it to send your scheduled messages\n\n"
    "Continue?"
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

    connected = await is_user_connected(uid)
    connect_hint = (
        "\n/connect — link your personal account for sending"
        if not connected
        else "\n/disconnect — unlink your personal account"
    )

    await message.answer(
        "👋 <b>Message Scheduler Bot</b>\n\n"
        "I generate AI messages and send them on a schedule.\n\n"
        "Commands:\n"
        "/schedule — create a new scheduled message\n"
        "/list — view your active schedules\n"
        "/cancel — cancel a schedule\n"
        f"{connect_hint}\n"
        "/help — show this message",
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await cmd_start(message)


# ── /connect ──────────────────────────────────────────────────────────────────


@router.message(Command("connect"))
async def cmd_connect(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return
    if not await _is_approved(message.from_user.id):
        return

    if await is_user_connected(message.from_user.id):
        await message.answer(
            "Your account is already connected. "
            "Use /disconnect to unlink it first."
        )
        return

    await state.clear()
    await message.answer(
        _CONNECT_WARNING, reply_markup=connect_confirm_keyboard(), parse_mode="HTML"
    )


@router.callback_query(F.data == "connect_confirm")
async def cb_connect_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user is None or callback.message is None:
        return
    await callback.message.edit_reply_markup()  # type: ignore[union-attr]
    await state.set_state(TelethonAuth.waiting_for_phone)
    await callback.message.answer(
        "📱 Enter your phone number in international format:\n"
        "<code>+1234567890</code>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "connect_cancel")
async def cb_connect_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_reply_markup()  # type: ignore[union-attr]
    await callback.message.answer("Cancelled.")  # type: ignore[union-attr]
    await callback.answer()


@router.message(TelethonAuth.waiting_for_phone)
async def auth_phone(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return
    phone = (message.text or "").strip()
    if not phone.startswith("+") or len(phone) < 8:
        await message.answer("Please enter a valid phone number starting with +")
        return

    try:
        phone_hash = await start_user_auth(message.from_user.id, phone)
    except Exception:
        logger.exception("start_user_auth failed for %d", message.from_user.id)
        await message.answer("Failed to send code. Check your phone number and try again.")
        await state.clear()
        return

    await state.update_data(phone=phone, phone_hash=phone_hash)
    await state.set_state(TelethonAuth.waiting_for_code)
    await message.answer(
        "A verification code was sent to your Telegram app.\n\n"
        "Enter the code (digits only, e.g. <code>12345</code>):",
        parse_mode="HTML",
    )


@router.message(TelethonAuth.waiting_for_code)
async def auth_code(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return
    code = (message.text or "").strip().replace(" ", "")
    data = await state.get_data()

    result = await complete_user_code(
        message.from_user.id, data["phone"], code, data["phone_hash"]
    )

    if result == "ok":
        await set_session_status(message.from_user.id, True)
        await state.clear()
        await message.answer(
            "✅ <b>Account connected!</b>\n\n"
            "You can now choose <i>From my account</i> when creating a schedule.",
            parse_mode="HTML",
        )
    elif result == "2fa":
        await state.set_state(TelethonAuth.waiting_for_2fa)
        await message.answer(
            "🔐 Your account has Two-Factor Authentication enabled.\n"
            "Enter your 2FA password:"
        )
    elif result == "expired":
        await state.clear()
        await message.answer("The code expired. Run /connect to start over.")
    else:
        await message.answer("Incorrect code. Try again:")


@router.message(TelethonAuth.waiting_for_2fa)
async def auth_2fa(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return
    password = (message.text or "").strip()
    ok = await complete_user_2fa(message.from_user.id, password)
    if ok:
        await set_session_status(message.from_user.id, True)
        await state.clear()
        await message.answer(
            "✅ <b>Account connected!</b>\n\n"
            "You can now choose <i>From my account</i> when creating a schedule.",
            parse_mode="HTML",
        )
    else:
        await message.answer("Wrong password. Try again:")


# ── /disconnect ───────────────────────────────────────────────────────────────


@router.message(Command("disconnect"))
async def cmd_disconnect(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return
    if not await _is_approved(message.from_user.id):
        return

    uid = message.from_user.id
    if not await is_user_connected(uid):
        await message.answer("No account connected. Use /connect to link one.")
        return

    await state.clear()
    await disconnect_user(uid)
    await set_session_status(uid, False)
    await message.answer(
        "🔌 Account disconnected. Your session has been deleted from the server.\n\n"
        "Remember to also revoke it in: "
        "<b>Telegram → Settings → Privacy and Security → Active Sessions</b>",
        parse_mode="HTML",
    )


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

    if active:
        await message.answer(f"<b>Active users ({len(active)})</b>", parse_mode="HTML")
        for u in active:
            display = f"@{u.username}" if u.username else u.first_name
            session_flag = " 🔗" if u.has_telethon_session else ""
            await message.answer(
                f"• {u.first_name} {display}{session_flag} — <code>{u.telegram_id}</code>",
                reply_markup=block_keyboard(u.telegram_id),
                parse_mode="HTML",
            )

    if blocked:
        await message.answer(f"<b>Blocked users ({len(blocked)})</b>", parse_mode="HTML")
        for u in blocked:
            display = f"@{u.username}" if u.username else u.first_name
            await message.answer(
                f"• {u.first_name} {display} — <code>{u.telegram_id}</code>",
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
    if callback.from_user is None:
        return
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
    step = "6" if data.get("interval_type") != "window" else "5"
    await state.set_state(ScheduleForm.waiting_for_send_as)
    await message.answer(
        f"Step {step} — <b>How should the message be sent?</b>\n\n"
        "Choose who sends the message:",
        reply_markup=send_as_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("send_as:"), ScheduleForm.waiting_for_send_as)
async def process_send_as(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user is None or callback.message is None:
        return

    send_as = callback.data.split(":")[1]  # type: ignore[union-attr]

    if send_as == "user":
        connected = await is_user_connected(callback.from_user.id)
        if not connected:
            await callback.answer(
                "You haven't connected your account yet. "
                "Run /connect first, then come back to /schedule.",
                show_alert=True,
            )
            return

    await state.update_data(send_as=send_as)
    await callback.message.edit_reply_markup()  # type: ignore[union-attr]

    data = await state.get_data()
    await state.set_state(ScheduleForm.waiting_for_confirm)

    jitter = data.get("jitter_seconds")
    jitter_line = (
        f"• Randomization: {_JITTER_LABELS.get(jitter, f'+{jitter}s')}\n" if jitter else ""
    )
    send_as_label = "🤖 From the bot" if send_as == "bot" else "👤 From my account"
    notice = f"\n\n{_BOT_SEND_NOTICE}" if send_as == "bot" else ""

    await callback.message.answer(
        "📋 <b>Confirm your schedule:</b>\n\n"
        f"• Recipient: <code>{data['target']}</code>\n"
        f"• Frequency: {data['interval_label']}\n"
        f"{jitter_line}"
        f"• Language: {data.get('language', 'English')}\n"
        f"• Topic: <i>{data['topic']}</i>\n"
        f"• Send as: {send_as_label}\n\n"
        f"Ready to activate?{notice}",
        reply_markup=confirm_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "confirm_yes", ScheduleForm.waiting_for_confirm)
async def confirm_yes(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user is None:
        return
    data = await state.get_data()
    await state.clear()
    await callback.message.edit_reply_markup()  # type: ignore[union-attr]

    jitter: int | None = data.get("jitter_seconds")
    language: str = data.get("language", "English")
    send_as: str = data.get("send_as", "bot")

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
            send_as=send_as,
        )
        send_as_label = "🤖 bot" if send_as == "bot" else "👤 your account"
        await callback.message.answer(  # type: ignore[union-attr]
            f"✅ Schedule created! (ID: <code>{task.id}</code>)\n"
            f"Sending to {task.target_username} — {task.interval_label} — "
            f"{task.language} — via {send_as_label}.",
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

    tasks = await list_active_tasks(message.from_user.id)
    if not tasks:
        await message.answer("No active schedules. Use /schedule to create one.")
        return

    for task in tasks:
        last = task.last_sent_at.strftime("%Y-%m-%d %H:%M UTC") if task.last_sent_at else "never"
        send_as_label = "🤖 bot" if task.send_as == "bot" else "👤 your account"
        text = (
            f"🗓 <b>Schedule #{task.id}</b>\n"
            f"• To: <code>{task.target_username}</code>\n"
            f"• Frequency: {task.interval_label}\n"
            f"• Language: {task.language}\n"
            f"• Send as: {send_as_label}\n"
            f"• Topic: <i>{task.topic}</i>\n"
            f"• Last sent: {last}"
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
    success = await cancel_task(task_id, callback.from_user.id)
    await callback.message.edit_reply_markup()  # type: ignore[union-attr]
    if success:
        await callback.message.answer(f"🗑 Schedule #{task_id} cancelled.")  # type: ignore[union-attr]
    else:
        await callback.message.answer(f"Schedule #{task_id} not found.")  # type: ignore[union-attr]
    await callback.answer()
