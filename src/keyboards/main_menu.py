"""Main menu keyboard."""
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# Main menu keyboard with operation buttons
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="Приход имущества"),
            KeyboardButton(text="Расход имущества")
        ],
        [
            KeyboardButton(text="Списание имущества"),
            KeyboardButton(text="Инвентаризация")
        ],
        [
            KeyboardButton(text="Передача имущества"),
            KeyboardButton(text="Возврат имущества")
        ],
    ],
    resize_keyboard=True
)
