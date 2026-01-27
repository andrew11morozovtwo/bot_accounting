"""User registration handlers."""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()


@router.message(Command("register"))
async def user_reg_handler(message: Message):
    """User registration handler stub."""
    await message.answer("Регистрация пользователя в разработке")
