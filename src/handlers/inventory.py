"""Inventory handlers."""
import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from src.services.db import get_user_by_telegram_id, UserRole

logger = logging.getLogger(__name__)
router = Router()


def check_user_registered(user_role: str) -> bool:
    """Check if user is registered (not UNKNOWN)."""
    return user_role != UserRole.UNKNOWN.value


@router.message(Command("inventory"))
async def inventory_handler(message: Message):
    """Inventory handler stub."""
    await message.answer("Учет товаров в разработке")


@router.message(F.text == "Инвентаризация")
async def inventory_operation_handler(message: Message):
    """Handle inventory operation."""
    user = message.from_user
    if not user:
        await message.answer("Ошибка: не удалось получить информацию о пользователе")
        return
    
    db_user = get_user_by_telegram_id(user.id)
    if not db_user or not check_user_registered(db_user.role):
        await message.answer(
            "❌ У вас нет доступа к этой операции.\n\n"
            "⏳ Ваш аккаунт ожидает одобрения администратором.\n"
            "После одобрения вам будет предоставлен доступ к операциям."
        )
        return
    
    await message.answer(
        "📋 <b>Инвентаризация</b>\n\n"
        "Эта операция позволяет провести инвентаризацию имущества на складе.\n\n"
        "Функционал в разработке...",
        parse_mode="HTML"
    )
    logger.info(f"User {message.from_user.id} started inventory operation")
