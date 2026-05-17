from aiogram.fsm.state import State, StatesGroup


class ScheduleForm(StatesGroup):
    waiting_for_target = State()
    waiting_for_interval = State()
    waiting_for_timezone = State()
    waiting_for_randomization = State()
    waiting_for_repeat_count = State()
    waiting_for_mode = State()
    waiting_for_media_type = State()
    waiting_for_media = State()
    waiting_for_language = State()
    waiting_for_topic = State()
    waiting_for_messages = State()
    waiting_for_confirm = State()


class EditForm(StatesGroup):
    waiting_for_target = State()
    waiting_for_topic = State()
    waiting_for_language = State()
    waiting_for_interval = State()
    waiting_for_messages = State()
