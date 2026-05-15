from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def _add_nav_row(builder: InlineKeyboardBuilder, show_back: bool = True) -> None:
    buttons: list[InlineKeyboardButton] = []
    if show_back:
        buttons.append(InlineKeyboardButton(text="⬅️ Back", callback_data="wizard_back"))
    buttons.append(InlineKeyboardButton(text="❌ Cancel", callback_data="wizard_cancel"))
    builder.row(*buttons)


def nav_keyboard(show_back: bool = True) -> InlineKeyboardMarkup:
    """Small navigation keyboard for text-input wizard steps."""
    builder = InlineKeyboardBuilder()
    if show_back:
        builder.button(text="⬅️ Back", callback_data="wizard_back")
    builder.button(text="❌ Cancel", callback_data="wizard_cancel")
    builder.adjust(2 if show_back else 1)
    return builder.as_markup()


TIMEZONE_OPTIONS: list[tuple[str, str]] = [
    ("🌐 UTC", "UTC"),
    ("🇺🇸 New York", "America/New_York"),
    ("🇺🇸 Chicago", "America/Chicago"),
    ("🇺🇸 Denver", "America/Denver"),
    ("🇺🇸 Los Angeles", "America/Los_Angeles"),
    ("🇧🇷 São Paulo", "America/Sao_Paulo"),
    ("🇬🇧 London", "Europe/London"),
    ("🇫🇷 Paris", "Europe/Paris"),
    ("🇩🇪 Berlin", "Europe/Berlin"),
    ("🇷🇺 Moscow", "Europe/Moscow"),
    ("🇦🇲 Yerevan", "Asia/Yerevan"),
    ("🇺🇦 Kyiv", "Europe/Kyiv"),
    ("🇦🇪 Dubai", "Asia/Dubai"),
    ("🇮🇳 Kolkata", "Asia/Kolkata"),
    ("🇨🇳 Shanghai", "Asia/Shanghai"),
    ("🇯🇵 Tokyo", "Asia/Tokyo"),
    ("🇰🇷 Seoul", "Asia/Seoul"),
    ("🇦🇺 Sydney", "Australia/Sydney"),
]

JITTER_OPTIONS: list[tuple[str, str]] = [
    ("No randomization", "jitter:0"),
    ("±15 minutes", "jitter:900"),
    ("±1 hour", "jitter:3600"),
    ("±2 hours", "jitter:7200"),
]

LANGUAGE_OPTIONS: list[tuple[str, str]] = [
    ("🇬🇧 English", "lang:English"),
    ("🇷🇺 Russian", "lang:Russian"),
    ("🇦🇲 Armenian", "lang:Armenian"),
    ("🇺🇦 Ukrainian", "lang:Ukrainian"),
    ("🇩🇪 German", "lang:German"),
    ("🇫🇷 French", "lang:French"),
    ("🇪🇸 Spanish", "lang:Spanish"),
    ("🇮🇹 Italian", "lang:Italian"),
]


def timezone_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for label, tz in TIMEZONE_OPTIONS:
        builder.button(text=label, callback_data=f"tz:{tz}")
    builder.adjust(2)
    _add_nav_row(builder)
    return builder.as_markup()


def edit_timezone_keyboard(task_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for label, tz in TIMEZONE_OPTIONS:
        builder.button(text=label, callback_data=f"edit_tz_val:{task_id}:{tz}")
    builder.adjust(2)
    return builder.as_markup()


def confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Confirm", callback_data="confirm_yes")
    builder.adjust(1)
    _add_nav_row(builder)
    return builder.as_markup()


def task_keyboard(task_id: int, is_paused: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="▶ Send now", callback_data=f"send_now:{task_id}")
    builder.button(text="🔍 Preview", callback_data=f"preview:{task_id}")
    if is_paused:
        builder.button(text="▶ Resume", callback_data=f"resume_task:{task_id}")
    else:
        builder.button(text="⏸ Pause", callback_data=f"pause_task:{task_id}")
    builder.button(text="✏️ Edit", callback_data=f"edit_task:{task_id}")
    builder.button(text="📋 History", callback_data=f"history:{task_id}")
    builder.button(text="🗑 Cancel this task", callback_data=f"cancel_task:{task_id}")
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()


def edit_language_keyboard(task_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for label, data in LANGUAGE_OPTIONS:
        lang = data.split(":")[1]
        builder.button(text=label, callback_data=f"edit_lang_val:{task_id}:{lang}")
    builder.adjust(2)
    return builder.as_markup()


def randomization_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for label, data in JITTER_OPTIONS:
        builder.button(text=label, callback_data=data)
    builder.adjust(2)
    _add_nav_row(builder)
    return builder.as_markup()


def repeat_count_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="♾ Unlimited", callback_data="repeat:0")
    builder.button(text="5 times", callback_data="repeat:5")
    builder.button(text="10 times", callback_data="repeat:10")
    builder.button(text="20 times", callback_data="repeat:20")
    builder.adjust(2)
    _add_nav_row(builder)
    return builder.as_markup()


def language_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for label, data in LANGUAGE_OPTIONS:
        builder.button(text=label, callback_data=data)
    builder.adjust(2)
    _add_nav_row(builder)
    return builder.as_markup()


def message_mode_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🤖 AI-generated", callback_data="mode:ai")
    builder.button(text="✍️ Exact message", callback_data="mode:exact")
    builder.adjust(2)
    _add_nav_row(builder)
    return builder.as_markup()


def edit_field_keyboard(
    task_id: int, message_mode: str = "ai", interval_type: str = "interval"
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if message_mode == "exact":
        builder.button(text="📝 Messages", callback_data=f"edit_messages:{task_id}")
    else:
        builder.button(text="📝 Topic", callback_data=f"edit_topic:{task_id}")
        builder.button(text="🌐 Language", callback_data=f"edit_lang:{task_id}")
    builder.button(text="⏱ Frequency", callback_data=f"edit_freq:{task_id}")
    if interval_type != "interval":
        builder.button(text="🕐 Timezone", callback_data=f"edit_tz:{task_id}")
    builder.button(text="📮 Recipient", callback_data=f"edit_target:{task_id}")
    builder.adjust(2)
    return builder.as_markup()


def block_keyboard(telegram_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🚫 Block", callback_data=f"block_user:{telegram_id}")
    return builder.as_markup()


def unblock_keyboard(telegram_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Unblock", callback_data=f"unblock_user:{telegram_id}")
    return builder.as_markup()


def active_user_keyboard(telegram_id: int, is_admin: bool) -> InlineKeyboardMarkup:
    """Master-admin view: block + grant/revoke admin."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🚫 Block", callback_data=f"block_user:{telegram_id}")
    if is_admin:
        builder.button(text="👑 Remove admin", callback_data=f"revoke_admin:{telegram_id}")
    else:
        builder.button(text="👑 Grant admin", callback_data=f"grant_admin:{telegram_id}")
    builder.adjust(2)
    return builder.as_markup()
