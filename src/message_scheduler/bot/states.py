from aiogram.fsm.state import State, StatesGroup


class ScheduleForm(StatesGroup):
    waiting_for_target = State()
    waiting_for_interval = State()
    waiting_for_randomization = State()
    waiting_for_language = State()
    waiting_for_topic = State()
    waiting_for_send_as = State()
    waiting_for_confirm = State()


class TelethonAuth(StatesGroup):
    waiting_for_phone = State()
    waiting_for_code = State()
    waiting_for_2fa = State()
