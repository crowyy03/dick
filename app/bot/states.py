from aiogram.fsm.state import State, StatesGroup


class AdminBindStates(StatesGroup):
    waiting_telegram_id = State()
    waiting_slot = State()
