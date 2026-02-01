"""FSM states for outgoing operation."""
from aiogram.fsm.state import State, StatesGroup


class OutgoingStates(StatesGroup):
    """States for outgoing operation flow."""
    waiting_for_asset_selection = State()  # Ожидание выбора актива (код или список)
    waiting_for_asset_code = State()  # Ожидание ввода кода актива
    waiting_for_recipient = State()  # Ожидание выбора получателя
    waiting_for_qty = State()  # Ожидание ввода количества
    waiting_for_confirm = State()  # Ожидание подтверждения
