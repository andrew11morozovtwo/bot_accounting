"""Start command handler."""
import logging
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from src.services.db import (
    get_user_by_telegram_id,
    create_user,
    count_users,
    UserRole,
    UserStatus
)
from src.keyboards.main_menu import main_menu

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message):
    """Handle /start command."""
    user = message.from_user
    if not user:
        await message.answer("Ошибка: не удалось получить информацию о пользователе")
        return
    
    telegram_id = user.id
    fullname = user.full_name or user.first_name or "Unknown User"
    
    # Check if user already exists
    existing_user = get_user_by_telegram_id(telegram_id)
    
    if existing_user:
        # User already registered
        role_text = {
            UserRole.SYSTEM_ADMIN.value: "Системный администратор",
            UserRole.MANAGER.value: "Менеджер",
            UserRole.STOREKEEPER.value: "Кладовщик",
            UserRole.FOREMAN.value: "Прораб",
            UserRole.WORKER.value: "Рабочий",
            UserRole.UNKNOWN.value: "Не зарегистрирован"
        }.get(existing_user.role, existing_user.role)
        
        # Check if user is registered (not UNKNOWN)
        if existing_user.role == UserRole.UNKNOWN.value:
            await message.answer(
                f"Добро пожаловать, {fullname}!\n"
                f"Ваша роль: {role_text}\n"
                f"Статус: {existing_user.status}\n\n"
                f"⏳ Ваш аккаунт ожидает одобрения администратором.\n"
                f"После одобрения вам будет предоставлен доступ к операциям."
            )
        else:
            await message.answer(
                f"Добро пожаловать, {fullname}!\n"
                f"Ваша роль: {role_text}\n"
                f"Статус: {existing_user.status}\n\n"
                f"Выберите операцию из меню:",
                reply_markup=main_menu
            )
        logger.info(f"User {telegram_id} ({fullname}) already exists with role {existing_user.role}")
        return
    
    # User doesn't exist - register them
    user_count = count_users()
    
    if user_count == 0:
        # First user becomes admin
        new_user = create_user(
            telegram_id=telegram_id,
            fullname=fullname,
            role=UserRole.SYSTEM_ADMIN.value,
            status=UserStatus.ACTIVE.value
        )
        role_text = "Системный администратор"
        logger.info(f"First user {telegram_id} ({fullname}) created as SYSTEM_ADMIN")
    else:
        # Regular user - create with default role
        new_user = create_user(
            telegram_id=telegram_id,
            fullname=fullname,
            role=UserRole.UNKNOWN.value,
            status=UserStatus.ACTIVE.value
        )
        role_text = "Не зарегистрирован (ожидает одобрения)"
        logger.info(f"New user {telegram_id} ({fullname}) created with role UNKNOWN")
    
    # Check if user is registered (not UNKNOWN)
    if new_user.role == UserRole.UNKNOWN.value:
        await message.answer(
            f"Добро пожаловать, {fullname}!\n"
            f"Вы успешно зарегистрированы.\n"
            f"Ваша роль: {role_text}\n"
            f"Статус: {new_user.status}\n\n"
            f"⏳ Ваш аккаунт ожидает одобрения администратором.\n"
            f"После одобрения вам будет предоставлен доступ к операциям."
        )
    else:
        await message.answer(
            f"Добро пожаловать, {fullname}!\n"
            f"Вы успешно зарегистрированы.\n"
            f"Ваша роль: {role_text}\n"
            f"Статус: {new_user.status}\n\n"
            f"Выберите операцию из меню:",
            reply_markup=main_menu
        )


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Handle /help command with role-based content."""
    user = message.from_user
    if not user:
        await message.answer("Ошибка: не удалось получить информацию о пользователе")
        return
    
    telegram_id = user.id
    
    # Get user from database
    db_user = get_user_by_telegram_id(telegram_id)
    
    if not db_user:
        # User not registered - show basic help
        help_text = (
            "📋 Доступные команды:\n\n"
            "/start - Регистрация в системе\n"
            "/help - Показать эту справку\n\n"
            "Для доступа к функциям бота необходимо зарегистрироваться."
        )
    else:
        # Check if user is admin
        is_admin = db_user.role in [
            UserRole.SYSTEM_ADMIN.value,
            UserRole.MANAGER.value
        ]
        
        if is_admin:
            # Admin help - full list
            help_text = (
                "📋 Доступные команды (Администратор):\n\n"
                "🔹 Основные:\n"
                "/start - Регистрация/информация о пользователе\n"
                "/help - Показать эту справку\n\n"
                "🔹 Администрирование:\n"
                "/admin - Админ-панель\n"
                "/register - Регистрация пользователей\n\n"
                "🔹 Операции:\n"
                "/operations - Управление операциями\n"
                "/inventory - Учет товаров\n\n"
                "📝 Примечание: Полный функционал находится в разработке."
            )
        else:
            # Regular user help - limited list
            help_text = (
                "📋 Доступные команды:\n\n"
                "/start - Регистрация/информация о пользователе\n"
                "/help - Показать эту справку\n\n"
                "📝 Ваша роль: {role_text}\n"
                "Для доступа к дополнительным функциям обратитесь к администратору."
            ).format(
                role_text={
                    UserRole.STOREKEEPER.value: "Кладовщик",
                    UserRole.FOREMAN.value: "Прораб",
                    UserRole.WORKER.value: "Рабочий",
                    UserRole.UNKNOWN.value: "Не зарегистрирован (ожидает одобрения)"
                }.get(db_user.role, db_user.role)
            )
    
    await message.answer(help_text)
    logger.info(f"Help command executed by user {telegram_id} (role: {db_user.role if db_user else 'not registered'})")
