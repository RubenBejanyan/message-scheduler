from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


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
