"""Inventory handlers."""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()


@router.message(Command("inventory"))
async def inventory_handler(message: Message):
    """Inventory handler stub."""
    await message.answer("Учет товаров в разработке")
