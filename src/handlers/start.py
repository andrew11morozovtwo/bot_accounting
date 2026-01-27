"""Start command handler."""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message, user_role: str = "unknown"):
    """Handle /start command."""
    await message.answer(f"Бот запущен, функционал в разработке\nВаша роль: {user_role}")
