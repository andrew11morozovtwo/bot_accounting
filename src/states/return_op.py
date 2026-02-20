"""FSM states for return operation (return to warehouse)."""
from aiogram.fsm.state import State, StatesGroup


class ReturnStates(StatesGroup):
    """States for return operation (asset back to warehouse)."""
    waiting_for_asset = State()    # Выбор актива у пользователя
    waiting_for_qty = State()      # Количество для возврата
    waiting_for_confirm = State()  # Подтверждение
    waiting_for_storekeeper_photo = State()  # Кладовщик отправляет фото перед подтверждением возврата
