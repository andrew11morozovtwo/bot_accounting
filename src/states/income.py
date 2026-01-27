"""FSM states for income operation."""
from aiogram.fsm.state import State, StatesGroup


class IncomeStates(StatesGroup):
    """States for income operation flow."""
    waiting_for_name = State()  # Ожидание названия имущества
    waiting_for_qty = State()  # Ожидание количества
    waiting_for_category = State()  # Ожидание выбора категории
    waiting_for_new_category = State()  # Ожидание ввода новой категории
    waiting_for_instances = State()  # Ожидание ввода особенностей для экземпляров
    waiting_for_instance_features = State()  # Ожидание ввода особенностей для конкретного экземпляра
    waiting_for_photo_mode = State()  # Ожидание выбора режима фото (одна на партию или для каждого)
    waiting_for_batch_photo = State()  # Ожидание одной фото на всю партию
    waiting_for_batch_price = State()  # Ожидание цены после batch фото
    waiting_for_instance_photo = State()  # Ожидание фото для конкретного экземпляра
    waiting_for_instance_price = State()  # Ожидание цены после фото экземпляра
    waiting_for_code = State()  # Ожидание кода/артикула
    waiting_for_confirm = State()  # Ожидание подтверждения
