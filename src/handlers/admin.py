"""Admin handlers."""
import logging
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.services.db import (
    get_user_by_telegram_id,
    get_all_users,
    get_user_by_id,
    update_user,
    UserRole,
    UserStatus
)

logger = logging.getLogger(__name__)
router = Router()


def check_admin(user_role: str) -> bool:
    """Check if user has admin privileges."""
    return user_role in [UserRole.SYSTEM_ADMIN.value, UserRole.MANAGER.value]


@router.message(Command("admin"))
async def admin_handler(message: Message):
    """Admin panel main menu."""
    user = message.from_user
    if not user:
        await message.answer("Ошибка: не удалось получить информацию о пользователе")
        return
    
    db_user = get_user_by_telegram_id(user.id)
    if not db_user or not check_admin(db_user.role):
        await message.answer("❌ У вас нет прав доступа к админ-панели.")
        return
    
    admin_text = (
        "🔐 Админ-панель\n\n"
        "Доступные команды:\n"
        "/users - Список всех пользователей\n"
        "/admin - Показать это меню\n\n"
        "Используйте команды для управления системой."
    )
    await message.answer(admin_text)


@router.message(Command("users"))
async def users_list_handler(message: Message):
    """Show list of all users."""
    user = message.from_user
    if not user:
        await message.answer("Ошибка: не удалось получить информацию о пользователе")
        return
    
    db_user = get_user_by_telegram_id(user.id)
    if not db_user or not check_admin(db_user.role):
        await message.answer("❌ У вас нет прав доступа к этой команде.")
        return
    
    users = get_all_users()
    if not users:
        await message.answer("📋 Пользователей в системе пока нет.")
        return
    
    # Build message with users list
    users_text = "📋 Список пользователей:\n\n"
    
    role_names = {
        UserRole.SYSTEM_ADMIN.value: "Системный администратор",
        UserRole.MANAGER.value: "Менеджер",
        UserRole.STOREKEEPER.value: "Кладовщик",
        UserRole.FOREMAN.value: "Прораб",
        UserRole.WORKER.value: "Рабочий",
        UserRole.UNKNOWN.value: "Не зарегистрирован"
    }
    
    # Build inline keyboard with buttons for each user
    builder = InlineKeyboardBuilder()
    
    for user_obj in users:
        role_name = role_names.get(user_obj.role, user_obj.role)
        status_icon = "✅" if user_obj.status == UserStatus.ACTIVE.value else "❌"
        users_text += (
            f"{status_icon} <b>{user_obj.fullname}</b>\n"
            f"   ID: {user_obj.id} | Telegram ID: {user_obj.telegram_id}\n"
            f"   Роль: {role_name}\n"
            f"   Статус: {user_obj.status}\n\n"
        )
        
        # Add button to change role for this user
        builder.button(
            text=f"Изменить роль: {user_obj.fullname}",
            callback_data=f"change_role_{user_obj.id}"
        )
    
    builder.adjust(1)  # One button per row
    
    await message.answer(users_text, reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(lambda c: c.data.startswith("change_role_"))
async def change_role_callback(callback: CallbackQuery):
    """Handle role change callback."""
    user = callback.from_user
    if not user:
        await callback.answer("Ошибка: не удалось получить информацию о пользователе")
        return
    
    db_user = get_user_by_telegram_id(user.id)
    if not db_user or not check_admin(db_user.role):
        await callback.answer("❌ У вас нет прав доступа.", show_alert=True)
        return
    
    # Extract user ID from callback data
    user_id = int(callback.data.split("_")[-1])
    target_user = get_user_by_id(user_id)
    
    if not target_user:
        await callback.answer("❌ Пользователь не найден.", show_alert=True)
        return
    
    # Build keyboard with available roles
    builder = InlineKeyboardBuilder()
    
    roles = [
        (UserRole.SYSTEM_ADMIN.value, "Системный администратор"),
        (UserRole.MANAGER.value, "Менеджер"),
        (UserRole.STOREKEEPER.value, "Кладовщик"),
        (UserRole.FOREMAN.value, "Прораб"),
        (UserRole.WORKER.value, "Рабочий"),
        (UserRole.UNKNOWN.value, "Не зарегистрирован")
    ]
    
    for role_value, role_name in roles:
        # Mark current role
        prefix = "✓ " if target_user.role == role_value else ""
        builder.button(
            text=f"{prefix}{role_name}",
            callback_data=f"set_role_{user_id}_{role_value}"
        )
    
    builder.button(
        text="❌ Отмена",
        callback_data=f"cancel_role_{user_id}"
    )
    builder.adjust(1)
    
    await callback.message.edit_text(
        f"Выберите новую роль для пользователя <b>{target_user.fullname}</b>:\n"
        f"Текущая роль: {target_user.role}",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("set_role_"))
async def set_role_callback(callback: CallbackQuery):
    """Handle setting new role."""
    user = callback.from_user
    if not user:
        await callback.answer("Ошибка: не удалось получить информацию о пользователе")
        return
    
    db_user = get_user_by_telegram_id(user.id)
    if not db_user or not check_admin(db_user.role):
        await callback.answer("❌ У вас нет прав доступа.", show_alert=True)
        return
    
    # Extract user ID and role from callback data
    parts = callback.data.split("_")
    user_id = int(parts[2])
    new_role = parts[3]
    
    target_user = get_user_by_id(user_id)
    if not target_user:
        await callback.answer("❌ Пользователь не найден.", show_alert=True)
        return
    
    # Update user role
    updated_user = update_user(user_id, role=new_role)
    if updated_user:
        role_names = {
            UserRole.SYSTEM_ADMIN.value: "Системный администратор",
            UserRole.MANAGER.value: "Менеджер",
            UserRole.STOREKEEPER.value: "Кладовщик",
            UserRole.FOREMAN.value: "Прораб",
            UserRole.WORKER.value: "Рабочий",
            UserRole.UNKNOWN.value: "Не зарегистрирован"
        }
        
        await callback.message.edit_text(
            f"✅ Роль пользователя <b>{updated_user.fullname}</b> изменена на:\n"
            f"<b>{role_names.get(new_role, new_role)}</b>",
            parse_mode="HTML"
        )
        await callback.answer("✅ Роль успешно изменена!")
        logger.info(f"Admin {user.id} changed role of user {user_id} to {new_role}")
        
        # Send notification to the user whose role was changed
        try:
            notification_text = (
                f"🔔 <b>Уведомление</b>\n\n"
                f"Ваша роль в системе была изменена администратором.\n\n"
                f"Новая роль: <b>{role_names.get(new_role, new_role)}</b>"
            )
            await callback.bot.send_message(
                chat_id=updated_user.telegram_id,
                text=notification_text,
                parse_mode="HTML"
            )
            logger.info(f"Notification sent to user {updated_user.telegram_id} about role change")
        except Exception as e:
            logger.warning(f"Failed to send notification to user {updated_user.telegram_id}: {e}")
    else:
        await callback.answer("❌ Ошибка при изменении роли.", show_alert=True)


@router.callback_query(lambda c: c.data.startswith("cancel_role_"))
async def cancel_role_callback(callback: CallbackQuery):
    """Handle cancel role change."""
    await callback.message.delete()
    await callback.answer("Отменено")
