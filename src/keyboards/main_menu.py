"""Main menu keyboard."""
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# Main menu keyboard stub
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Операции")],
        [KeyboardButton(text="Учет товаров")],
        [KeyboardButton(text="Админ")],
    ],
    resize_keyboard=True
)
