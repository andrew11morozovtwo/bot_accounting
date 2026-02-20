"""FSM states for transfer operation."""
from aiogram.fsm.state import State, StatesGroup


class TransferStates(StatesGroup):
    """States for transfer operation (asset from one user to another)."""
    waiting_for_asset = State()      # Выбор актива, которым владеет пользователь
    waiting_for_recipient = State() # Выбор получателя
    waiting_for_qty = State()       # Количество для передачи
    waiting_for_confirm = State()   # Подтверждение
