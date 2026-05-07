from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

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


def confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Confirm", callback_data="confirm_yes")
    builder.button(text="❌ Cancel", callback_data="confirm_no")
    builder.adjust(2)
    return builder.as_markup()


def task_keyboard(task_id: int, is_paused: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="▶ Send now", callback_data=f"send_now:{task_id}")
    if is_paused:
        builder.button(text="▶ Resume", callback_data=f"resume_task:{task_id}")
    else:
        builder.button(text="⏸ Pause", callback_data=f"pause_task:{task_id}")
    builder.button(text="🗑 Cancel this task", callback_data=f"cancel_task:{task_id}")
    builder.adjust(1)
    return builder.as_markup()


def randomization_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for label, data in JITTER_OPTIONS:
        builder.button(text=label, callback_data=data)
    builder.adjust(2)
    return builder.as_markup()


def language_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for label, data in LANGUAGE_OPTIONS:
        builder.button(text=label, callback_data=data)
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
