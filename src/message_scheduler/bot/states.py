from aiogram.fsm.state import State, StatesGroup


class ScheduleForm(StatesGroup):
    waiting_for_target = State()
    waiting_for_interval = State()
    waiting_for_randomization = State()
    waiting_for_language = State()
    waiting_for_topic = State()
    waiting_for_confirm = State()
