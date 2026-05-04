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


def cancel_task_keyboard(task_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Cancel this task", callback_data=f"cancel_task:{task_id}")
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
