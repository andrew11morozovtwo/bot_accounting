"""Admin handlers."""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()


@router.message(Command("admin"))
async def admin_handler(message: Message):
    """Admin handler stub."""
    await message.answer("Админ-функционал в разработке")
