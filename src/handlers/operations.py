"""Operations handlers."""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()


@router.message(Command("operations"))
async def operations_handler(message: Message):
    """Operations handler stub."""
    await message.answer("Операции в разработке")
