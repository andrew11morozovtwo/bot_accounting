"""Operations handlers."""
import logging
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.services.db import (
    get_user_by_telegram_id,
    get_user_by_id,
    get_all_users,
    UserRole,
    create_asset,
    get_asset_by_code,
    get_asset_by_id,
    get_available_assets,
    update_asset,
    create_operation,
    OperationType,
    AssetState,
    get_all_categories,
    get_category_by_id,
    get_category_by_name,
    create_category,
    create_asset_instance,
    get_next_instance_number,
    get_available_asset_instances,
    get_asset_instances_assigned_to_user,
    update_asset_instance,
    update_operation_signature,
    get_unsigned_outgoing_operations,
    get_asset_instances_by_asset_id,
    get_operation_by_id,
    get_return_approver,
    create_pending_return,
    get_pending_return_by_id,
    update_pending_return_status,
    set_asset_first_income_photo_if_empty,
    add_asset_return_photo,
)
from src.states.income import IncomeStates
from src.states.outgoing import OutgoingStates
from src.states.transfer import TransferStates
from src.states.return_op import ReturnStates

logger = logging.getLogger(__name__)
router = Router()


def check_user_registered(user_role: str) -> bool:
    """Check if user is registered (not UNKNOWN)."""
    return user_role != UserRole.UNKNOWN.value


@router.message(Command("operations"))
async def operations_handler(message: Message):
    """Operations handler stub."""
    await message.answer("Операции в разработке")


@router.message(F.text == "Приход имущества")
async def income_handler(message: Message, state: FSMContext):
    """Start income operation flow."""
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
    
    # Start FSM flow
    await state.set_state(IncomeStates.waiting_for_name)
    await message.answer(
        "📥 <b>Приход имущества</b>\n\n"
        "Введите название имущества:",
        parse_mode="HTML"
    )
    logger.info(f"User {message.from_user.id} started income operation")


@router.message(IncomeStates.waiting_for_name)
async def process_name(message: Message, state: FSMContext):
    """Process asset name."""
    name = message.text.strip()
    if not name:
        await message.answer("❌ Название не может быть пустым. Пожалуйста, введите название имущества:")
        return
    
    await state.update_data(name=name)
    await state.set_state(IncomeStates.waiting_for_qty)
    await message.answer(
        f"✅ Название: <b>{name}</b>\n\n"
        "Введите количество:",
        parse_mode="HTML"
    )


@router.message(IncomeStates.waiting_for_qty)
async def process_qty(message: Message, state: FSMContext):
    """Process quantity."""
    try:
        qty = float(message.text.strip().replace(",", "."))
        if qty <= 0:
            raise ValueError("Quantity must be positive")
        if qty != int(qty):
            raise ValueError("Quantity must be integer")
        qty = int(qty)
    except ValueError:
        await message.answer("❌ Неверный формат количества. Введите целое число (например: 1, 5, 10):")
        return
    
    await state.update_data(qty=qty)
    await state.set_state(IncomeStates.waiting_for_category)
    
    # Get all categories
    categories = get_all_categories()
    builder = InlineKeyboardBuilder()
    
    for category in categories:
        builder.button(text=category.name, callback_data=f"category_{category.id}")
    
    builder.button(text="➕ Добавить категорию", callback_data="add_category")
    builder.adjust(2)  # Two buttons per row
    
    await message.answer(
        f"✅ Количество: <b>{qty}</b>\n\n"
        "Выберите категорию имущества:",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )


@router.callback_query(F.data.startswith("category_"), IncomeStates.waiting_for_category)
async def select_category(callback: CallbackQuery, state: FSMContext):
    """Select category from list."""
    category_id = int(callback.data.split("_")[1])
    category = get_category_by_id(category_id)
    
    if not category:
        await callback.answer("❌ Категория не найдена", show_alert=True)
        return
    
    await state.update_data(category_id=category_id, category_name=category.name)
    await state.set_state(IncomeStates.waiting_for_instances)
    
    data = await state.get_data()
    qty = data['qty']
    
    await callback.message.edit_text(
        f"✅ Категория: <b>{category.name}</b>\n\n"
        f"Теперь нужно указать отличительные особенности для каждого из <b>{qty}</b> экземпляров.\n\n"
        f"Введите особенности для экземпляра <b>#1</b> (например: 'синий', 'красный', 'большой')\n"
        f"или отправьте 'авто' для автоматической нумерации всех экземпляров:",
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "add_category", IncomeStates.waiting_for_category)
async def add_category_callback(callback: CallbackQuery, state: FSMContext):
    """Start adding new category."""
    await state.set_state(IncomeStates.waiting_for_new_category)
    await callback.message.edit_text(
        "Введите название новой категории:",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(IncomeStates.waiting_for_new_category)
async def process_new_category(message: Message, state: FSMContext):
    """Process new category name."""
    category_name = message.text.strip()
    
    if not category_name:
        await message.answer("❌ Название категории не может быть пустым. Введите название:")
        return
    
    # Check if category already exists
    existing = get_category_by_name(category_name)
    if existing:
        await message.answer(
            f"❌ Категория '{category_name}' уже существует. Выберите её из списка или введите другое название:"
        )
        return
    
    try:
        category = create_category(category_name)
        await state.update_data(category_id=category.id, category_name=category.name)
        await state.set_state(IncomeStates.waiting_for_instances)
        
        data = await state.get_data()
        qty = data['qty']
        
        await message.answer(
            f"✅ Категория '{category.name}' создана!\n\n"
            f"Теперь нужно указать отличительные особенности для каждого из <b>{qty}</b> экземпляров.\n\n"
            f"Введите особенности для экземпляра <b>#1</b> (например: 'синий', 'красный', 'большой')\n"
            f"или отправьте 'авто' для автоматической нумерации всех экземпляров:",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Error creating category: {e}", exc_info=True)
        await message.answer("❌ Ошибка при создании категории. Попробуйте ещё раз:")


@router.message(IncomeStates.waiting_for_instances)
async def process_instances(message: Message, state: FSMContext):
    """Process instances features input."""
    data = await state.get_data()
    qty = data['qty']
    text = message.text.strip().lower()
    
    # Initialize instances list if not exists
    if 'instances' not in data:
        data['instances'] = []
    
    instances = data['instances']
    current_index = len(instances)
    
    # If user sends "авто", generate auto-numbering for all remaining instances
    if text == "авто":
        # Generate auto-numbered features for all remaining instances
        for i in range(current_index, qty):
            instances.append(f"Экз. #{i + 1}")
        
        await state.update_data(instances=instances)
        await state.set_state(IncomeStates.waiting_for_photo_mode)
        
        instances_text = "\n".join([f"  {i+1}. {features}" for i, features in enumerate(instances)])
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📷 Одна фото на всю партию", callback_data="photo_mode_batch")
        builder.button(text="📸 Фото для каждого экземпляра", callback_data="photo_mode_individual")
        builder.button(text="⏭️ Пропустить фото", callback_data="skip_photo")
        builder.adjust(1)
        
        await message.answer(
            f"✅ Особенности для всех экземпляров:\n{instances_text}\n\n"
            "Выберите режим добавления фотографий:",
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
        return
    
    # Process manual input
    features = message.text.strip()
    if not features:
        await message.answer("❌ Особенности не могут быть пустыми. Введите особенности:")
        return
    
    instances.append(features)
    await state.update_data(instances=instances)
    
    # Check if all instances are filled
    if len(instances) >= qty:
        # All instances filled, move to photo mode selection
        await state.set_state(IncomeStates.waiting_for_photo_mode)
        
        instances_text = "\n".join([f"  {i+1}. {features}" for i, features in enumerate(instances)])
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📷 Одна фото на всю партию", callback_data="photo_mode_batch")
        builder.button(text="📸 Фото для каждого экземпляра", callback_data="photo_mode_individual")
        builder.button(text="⏭️ Пропустить фото", callback_data="skip_photo")
        builder.adjust(1)
        
        await message.answer(
            f"✅ Особенности для всех экземпляров:\n{instances_text}\n\n"
            "Выберите режим добавления фотографий:",
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
    else:
        # More instances needed
        next_index = len(instances) + 1
        await message.answer(
            f"✅ Экземпляр #{current_index + 1}: <b>{features}</b>\n\n"
            f"Введите особенности для экземпляра <b>#{next_index}</b>:\n"
            f"(или отправьте 'авто' для автоматической нумерации оставшихся)",
            parse_mode="HTML"
        )


@router.callback_query(F.data == "photo_mode_batch", IncomeStates.waiting_for_photo_mode)
async def photo_mode_batch(callback: CallbackQuery, state: FSMContext):
    """Set batch photo mode (one photo for all instances)."""
    await state.update_data(photo_mode="batch")
    await state.set_state(IncomeStates.waiting_for_batch_photo)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="⏭️ Пропустить", callback_data="skip_photo")
    
    await callback.message.edit_text(
        "📷 <b>Режим: одна фото на всю партию</b>\n\n"
        "Отправьте одно фото, которое будет привязано ко всем экземплярам:",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data == "photo_mode_individual", IncomeStates.waiting_for_photo_mode)
async def photo_mode_individual(callback: CallbackQuery, state: FSMContext):
    """Set individual photo mode (one photo per instance)."""
    data = await state.get_data()
    instances = data.get('instances', [])
    
    await state.update_data(photo_mode="individual", current_instance_index=0)
    await state.set_state(IncomeStates.waiting_for_instance_photo)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="⏭️ Пропустить для этого экземпляра", callback_data="skip_instance_photo")
    
    await callback.message.edit_text(
        f"📸 <b>Режим: фото для каждого экземпляра</b>\n\n"
        f"Экземпляр <b>#1: {instances[0]}</b>\n\n"
        "Отправьте фото для этого экземпляра:",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data == "skip_photo")
async def skip_photo(callback: CallbackQuery, state: FSMContext):
    """Skip photo step."""
    await state.update_data(batch_photo_file_id=None, instance_photos={}, batch_price=None, instance_prices={})
    await state.set_state(IncomeStates.waiting_for_code)
    await callback.message.edit_text(
        "✅ Фото: <i>не загружено</i>\n\n"
        "Введите код/артикул имущества:",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(IncomeStates.waiting_for_photo_mode, F.photo)
@router.message(IncomeStates.waiting_for_photo_mode, F.document)
async def income_photo_before_mode(message: Message, state: FSMContext):
    """Если пользователь отправил фото до выбора режима — считаем как «одна фото на партию»."""
    file_id = None
    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.document and message.document.mime_type and message.document.mime_type.startswith("image/"):
        file_id = message.document.file_id
    if not file_id:
        await message.answer(
            "❌ Отправьте изображение (фото или файл-картинку) или выберите режим выше."
        )
        return
    await state.update_data(photo_mode="batch", batch_photo_file_id=file_id)
    await state.set_state(IncomeStates.waiting_for_batch_price)
    builder = InlineKeyboardBuilder()
    builder.button(text="⏭️ Пропустить цену", callback_data="skip_batch_price")
    await message.answer(
        "✅ Фото загружено и будет привязано ко всем экземплярам\n\n"
        "Введите учетную цену за единицу в рублях (например: 1500.50):",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )


@router.message(IncomeStates.waiting_for_photo_mode)
async def income_photo_mode_other(message: Message, state: FSMContext):
    """Любое другое сообщение в выборе режима фото — подсказка."""
    await message.answer(
        "Выберите режим добавления фото кнопкой выше или отправьте одно фото — "
        "оно будет привязано ко всей партии."
    )


@router.message(IncomeStates.waiting_for_batch_price)
async def process_batch_price(message: Message, state: FSMContext):
    """Process price input after batch photo."""
    try:
        # Replace comma with dot and parse as float
        price_str = message.text.strip().replace(",", ".")
        price = float(price_str)
        
        if price < 0:
            raise ValueError("Price cannot be negative")
        
        # Round to 2 decimal places
        price = round(price, 2)
        
    except ValueError:
        await message.answer(
            "❌ Неверный формат цены. Введите число с точностью до 2 знаков после запятой\n"
            "(например: 1500.50 или 2000.00):"
        )
        return
    
    await state.update_data(batch_price=price)
    await state.set_state(IncomeStates.waiting_for_code)
    
    await message.answer(
        f"✅ Учетная цена: <b>{price:.2f} руб.</b> (будет применена ко всем экземплярам)\n\n"
        "Введите код/артикул имущества:",
        parse_mode="HTML"
    )


@router.callback_query(F.data == "skip_batch_price", IncomeStates.waiting_for_batch_price)
async def skip_batch_price(callback: CallbackQuery, state: FSMContext):
    """Skip batch price input."""
    await state.update_data(batch_price=None)
    await state.set_state(IncomeStates.waiting_for_code)
    await callback.message.edit_text(
        "✅ Учетная цена: <i>не указана</i>\n\n"
        "Введите код/артикул имущества:",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(IncomeStates.waiting_for_batch_photo, F.photo)
@router.message(IncomeStates.waiting_for_batch_photo, F.document)
async def process_batch_photo(message: Message, state: FSMContext):
    """Process batch photo (one photo for all instances). Принимаем и фото, и файл-картинку."""
    try:
        photo_file_id = None
        if message.photo:
            photo_file_id = message.photo[-1].file_id
        elif message.document and message.document.mime_type and message.document.mime_type.startswith("image/"):
            photo_file_id = message.document.file_id
        if not photo_file_id:
            await message.answer(
                "❌ Отправьте изображение (фото из галереи/камеры или файл-картинку) или нажмите «Пропустить»."
            )
            return
        await state.update_data(batch_photo_file_id=photo_file_id)
        await state.set_state(IncomeStates.waiting_for_batch_price)
        builder = InlineKeyboardBuilder()
        builder.button(text="⏭️ Пропустить цену", callback_data="skip_batch_price")
        await message.answer(
            "✅ Фото загружено и будет привязано ко всем экземплярам\n\n"
            "Введите учетную цену за единицу в рублях (например: 1500.50):",
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        logger.exception("process_batch_photo error: %s", e)
        await message.answer(
            "❌ Не удалось обработать фото. Попробуйте отправить ещё раз или нажмите «Пропустить»."
        )


@router.message(IncomeStates.waiting_for_batch_photo)
async def process_batch_photo_text(message: Message, state: FSMContext):
    """Handle text when batch photo expected."""
    await message.answer(
        "❌ Пожалуйста, отправьте фото (или файл-картинку) или нажмите «Пропустить»."
    )


@router.message(IncomeStates.waiting_for_instance_photo, F.photo)
@router.message(IncomeStates.waiting_for_instance_photo, F.document)
async def process_instance_photo(message: Message, state: FSMContext):
    """Process photo for individual instance. Принимаем и фото, и файл-картинку."""
    try:
        data = await state.get_data()
        instances = data.get('instances', [])
        current_index = data.get('current_instance_index', 0)
        if not instances or current_index >= len(instances):
            await message.answer("❌ Ошибка состояния. Начните приход заново (/start → Приход имущества).")
            await state.clear()
            return
        photo_file_id = None
        if message.photo:
            photo_file_id = message.photo[-1].file_id
        elif message.document and message.document.mime_type and message.document.mime_type.startswith("image/"):
            photo_file_id = message.document.file_id
        if not photo_file_id:
            await message.answer(
                "❌ Отправьте изображение (фото или файл-картинку) или нажмите «Пропустить для этого экземпляра»."
            )
            return
        if 'instance_photos' not in data:
            data['instance_photos'] = {}
        instance_photos = dict(data['instance_photos'])
        instance_photos[current_index] = photo_file_id
        await state.update_data(instance_photos=instance_photos)
        await state.set_state(IncomeStates.waiting_for_instance_price)
        builder = InlineKeyboardBuilder()
        builder.button(text="⏭️ Пропустить цену", callback_data="skip_instance_price")
        await message.answer(
            f"✅ Фото для экземпляра #{current_index + 1}: <b>{instances[current_index]}</b>\n\n"
            "Введите учетную цену для этого экземпляра в рублях (например: 1500.50):",
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        logger.exception("process_instance_photo error: %s", e)
        await message.answer(
            "❌ Не удалось обработать фото. Отправьте ещё раз или нажмите «Пропустить для этого экземпляра»."
        )


@router.message(IncomeStates.waiting_for_instance_price)
async def process_instance_price(message: Message, state: FSMContext):
    """Process price input for individual instance."""
    if not message.text or not message.text.strip():
        await message.answer(
            "❌ Нужно ввести цену числом (например: 1500.50). Отправьте текстовое сообщение."
        )
        return
    data = await state.get_data()
    instances = data.get('instances', [])
    current_index = data.get('current_instance_index', 0)

    try:
        # Replace comma with dot and parse as float
        price_str = message.text.strip().replace(",", ".")
        price = float(price_str)
        
        if price < 0:
            raise ValueError("Price cannot be negative")
        
        # Round to 2 decimal places
        price = round(price, 2)
        
    except ValueError:
        await message.answer(
            "❌ Неверный формат цены. Введите число с точностью до 2 знаков после запятой\n"
            "(например: 1500.50 или 2000.00):"
        )
        return
    
    # Initialize instance_prices dict if not exists
    if 'instance_prices' not in data:
        data['instance_prices'] = {}
    
    instance_prices = data['instance_prices']
    instance_prices[current_index] = price
    await state.update_data(instance_prices=instance_prices)
    
    current_index += 1
    
    # Check if all instances processed
    if current_index >= len(instances):
        # All instances processed, move to code step
        await state.set_state(IncomeStates.waiting_for_code)
        await message.answer(
            f"✅ Обработка фото и цен завершена для всех {len(instances)} экземпляров\n\n"
            "Введите код/артикул имущества:",
            parse_mode="HTML"
        )
    else:
        # More instances need processing
        await state.update_data(current_instance_index=current_index)
        
        builder = InlineKeyboardBuilder()
        builder.button(text="⏭️ Пропустить для этого экземпляра", callback_data="skip_instance_photo")
        
        await message.answer(
            f"✅ Цена для экземпляра #{current_index}: <b>{price:.2f} руб.</b>\n\n"
            f"Экземпляр <b>#{current_index + 1}: {instances[current_index]}</b>\n\n"
            "Отправьте фото для этого экземпляра:",
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )


@router.callback_query(F.data == "skip_instance_price", IncomeStates.waiting_for_instance_price)
async def skip_instance_price(callback: CallbackQuery, state: FSMContext):
    """Skip price for current instance."""
    data = await state.get_data()
    instances = data.get('instances', [])
    current_index = data.get('current_instance_index', 0)
    
    # Initialize instance_prices dict if not exists
    if 'instance_prices' not in data:
        data['instance_prices'] = {}
    
    instance_prices = data['instance_prices']
    instance_prices[current_index] = None  # Mark as skipped
    await state.update_data(instance_prices=instance_prices)
    
    current_index += 1
    
    # Check if all instances processed
    if current_index >= len(instances):
        # All instances processed, move to code step
        await state.set_state(IncomeStates.waiting_for_code)
        await callback.message.edit_text(
            f"✅ Обработка завершена для всех {len(instances)} экземпляров\n\n"
            "Введите код/артикул имущества:",
            parse_mode="HTML"
        )
    else:
        # More instances need processing
        await state.update_data(current_instance_index=current_index)
        
        builder = InlineKeyboardBuilder()
        builder.button(text="⏭️ Пропустить для этого экземпляра", callback_data="skip_instance_photo")
        
        await callback.message.edit_text(
            f"⏭️ Цена для экземпляра #{current_index} пропущена\n\n"
            f"Экземпляр <b>#{current_index + 1}: {instances[current_index]}</b>\n\n"
            "Отправьте фото для этого экземпляра:",
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
    
    await callback.answer()


@router.callback_query(F.data == "skip_instance_photo", IncomeStates.waiting_for_instance_photo)
async def skip_instance_photo(callback: CallbackQuery, state: FSMContext):
    """Skip photo and price for current instance."""
    data = await state.get_data()
    instances = data.get('instances', [])
    current_index = data.get('current_instance_index', 0)
    
    # Initialize dicts if not exists
    if 'instance_photos' not in data:
        data['instance_photos'] = {}
    if 'instance_prices' not in data:
        data['instance_prices'] = {}
    
    instance_photos = data['instance_photos']
    instance_prices = data['instance_prices']
    instance_photos[current_index] = None  # Mark as skipped
    instance_prices[current_index] = None  # Mark as skipped
    await state.update_data(instance_photos=instance_photos, instance_prices=instance_prices)
    
    current_index += 1
    
    # Check if all instances processed
    if current_index >= len(instances):
        # All instances processed, move to code step
        await state.set_state(IncomeStates.waiting_for_code)
        await callback.message.edit_text(
            f"✅ Обработка завершена для всех {len(instances)} экземпляров\n\n"
            "Введите код/артикул имущества:",
            parse_mode="HTML"
        )
    else:
        # More instances need processing
        await state.update_data(current_instance_index=current_index)
        
        builder = InlineKeyboardBuilder()
        builder.button(text="⏭️ Пропустить для этого экземпляра", callback_data="skip_instance_photo")
        
        await callback.message.edit_text(
            f"⏭️ Фото и цена для экземпляра #{current_index} пропущены\n\n"
            f"Экземпляр <b>#{current_index + 1}: {instances[current_index]}</b>\n\n"
            "Отправьте фото для этого экземпляра:",
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
    
    await callback.answer()


@router.message(IncomeStates.waiting_for_instance_photo)
async def process_instance_photo_text(message: Message, state: FSMContext):
    """Handle text or other content when instance photo expected."""
    await message.answer(
        "❌ Пожалуйста, отправьте фото (или файл-картинку) или нажмите «Пропустить для этого экземпляра»."
    )


@router.message(IncomeStates.waiting_for_instance_price)
async def process_instance_price_text(message: Message, state: FSMContext):
    """Handle text when instance price expected."""
    await message.answer(
        "❌ Пожалуйста, введите цену или нажмите 'Пропустить цену'."
    )


@router.message(IncomeStates.waiting_for_batch_price)
async def process_batch_price_text(message: Message, state: FSMContext):
    """Handle text when batch price expected."""
    await message.answer(
        "❌ Пожалуйста, введите цену или нажмите 'Пропустить цену'."
    )


@router.message(IncomeStates.waiting_for_code)
async def process_code(message: Message, state: FSMContext):
    """Process code."""
    code = message.text.strip()
    if not code:
        await message.answer("❌ Код не может быть пустым. Введите код/артикул имущества:")
        return
    
    await state.update_data(code=code)
    
    await state.update_data(code=code)
    
    # Get all data
    data = await state.get_data()
    
    # Show confirmation
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data="confirm_income")
    builder.button(text="❌ Отменить", callback_data="cancel_income")
    builder.adjust(1)
    
    # Format instances with prices
    instances = data.get('instances', [])
    photo_mode = data.get('photo_mode', 'none')
    batch_price = data.get('batch_price')
    instance_prices = data.get('instance_prices', {})
    
    instances_lines = []
    for idx, features in enumerate(instances):
        if photo_mode == "batch":
            price_text = f"{batch_price:.2f} руб." if batch_price is not None else "не указана"
            instances_lines.append(f"  {idx+1}. {features} - {price_text}")
        elif photo_mode == "individual":
            price = instance_prices.get(idx)
            price_text = f"{price:.2f} руб." if price is not None else "не указана"
            instances_lines.append(f"  {idx+1}. {features} - {price_text}")
        else:
            instances_lines.append(f"  {idx+1}. {features}")
    
    instances_text = "\n".join(instances_lines)
    
    # Determine photo status
    photo_status = "не загружено"
    if photo_mode == "batch":
        photo_status = f"одна фото на всю партию ({'загружено' if data.get('batch_photo_file_id') else 'не загружено'})"
    elif photo_mode == "individual":
        instance_photos = data.get('instance_photos', {})
        photos_count = sum(1 for v in instance_photos.values() if v is not None)
        photo_status = f"фото для каждого экземпляра ({photos_count}/{len(instances)} загружено)"
    
    summary = (
        f"📋 <b>Подтверждение операции</b>\n\n"
        f"Название: <b>{data['name']}</b>\n"
        f"Количество: <b>{data['qty']}</b>\n"
        f"Категория: <b>{data.get('category_name', 'не указана')}</b>\n"
        f"Код/артикул: <b>{code}</b>\n"
        f"Фото: {photo_status}\n\n"
        f"Экземпляры с ценами:\n{instances_text}\n\n"
        f"Подтвердите операцию:"
    )
    
    await state.set_state(IncomeStates.waiting_for_confirm)
    
    # Show photo if batch mode and photo exists
    if photo_mode == "batch" and data.get('batch_photo_file_id'):
        await message.answer_photo(
            photo=data['batch_photo_file_id'],
            caption=summary,
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
    else:
        await message.answer(
            summary,
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )


@router.callback_query(F.data == "confirm_income", IncomeStates.waiting_for_confirm)
async def confirm_income(callback: CallbackQuery, state: FSMContext):
    """Confirm and save income operation."""
    user = callback.from_user
    if not user:
        await callback.answer("Ошибка: не удалось получить информацию о пользователе")
        return
    
    db_user = get_user_by_telegram_id(user.id)
    if not db_user:
        await callback.answer("❌ Пользователь не найден в системе", show_alert=True)
        await state.clear()
        return
    
    data = await state.get_data()
    
    try:
        # Get instances features
        instances_features = data.get('instances', [])
        qty = data['qty']
        
        # Check if asset with this code already exists
        existing_asset = get_asset_by_code(data['code'])
        
        if existing_asset:
            # Update existing asset quantity only (price is stored in operation)
            new_qty = existing_asset.qty + qty
            asset = update_asset(
                asset_id=existing_asset.id,
                qty=new_qty,
                state=AssetState.IN_STOCK.value
            )
            logger.info(f"Updated existing asset {asset.id} (code: {data['code']}), new qty: {new_qty}")
            
            # If instances not filled or auto-numbering needed, generate numbers starting from max existing
            if len(instances_features) < qty:
                max_num = get_next_instance_number(asset.id) - 1
                start_num = len(instances_features) + 1
                for i in range(start_num, qty + 1):
                    instances_features.append(f"Экз. #{max_num + i}")
        else:
            # Create new asset (price is stored in operation, not in asset)
            asset = create_asset(
                name=data['name'],
                qty=qty,
                category_id=data.get('category_id'),
                code=data['code'],
                state=AssetState.IN_STOCK.value
            )
            logger.info(f"Created new asset {asset.id} (code: {data['code']})")
            
            # If instances not filled (shouldn't happen, but safety check)
            if len(instances_features) < qty:
                # Generate auto-numbering for missing instances
                start_num = len(instances_features) + 1
                for i in range(start_num, qty + 1):
                    instances_features.append(f"Экз. #{i}")
        
        # Get photo mode, photos, and prices
        photo_mode = data.get('photo_mode', 'none')
        batch_photo_file_id = data.get('batch_photo_file_id')
        batch_price = data.get('batch_price')
        instance_photos = data.get('instance_photos', {})
        instance_prices = data.get('instance_prices', {})
        
        # Create instances with photos and prices
        created_instances = []
        prices_list = []
        
        for idx, features in enumerate(instances_features):
            # Determine photo_file_id for this instance
            instance_photo_file_id = None
            if photo_mode == "batch" and batch_photo_file_id:
                # Batch mode: use same photo for all instances
                instance_photo_file_id = batch_photo_file_id
            elif photo_mode == "individual":
                # Individual mode: use specific photo for this instance
                instance_photo_file_id = instance_photos.get(idx)
            
            # Determine price for this instance
            instance_price = None
            if photo_mode == "batch":
                # Batch mode: use same price for all instances
                instance_price = batch_price
            elif photo_mode == "individual":
                # Individual mode: use specific price for this instance
                instance_price = instance_prices.get(idx)
            
            if instance_price is not None:
                prices_list.append(instance_price)
            
            instance = create_asset_instance(
                asset_id=asset.id,
                distinctive_features=features,
                state=AssetState.IN_STOCK.value,
                photo_file_id=instance_photo_file_id,
                price=instance_price
            )
            created_instances.append(instance)
            logger.info(f"Created instance {instance.id} for asset {asset.id} with features: {features}, price: {instance_price}, photo: {instance_photo_file_id is not None}")
        
        # Calculate average price for operation
        operation_price = None
        if prices_list:
            operation_price = sum(prices_list) / len(prices_list)
            operation_price = round(operation_price, 2)
        
        # Create operation (use batch photo if available, otherwise first individual photo)
        operation_photo_file_id = batch_photo_file_id
        if not operation_photo_file_id and instance_photos:
            # Use first available individual photo
            operation_photo_file_id = next((v for v in instance_photos.values() if v is not None), None)
        
        # Установить первую фото с прихода у актива, если ещё не задана
        if operation_photo_file_id:
            set_asset_first_income_photo_if_empty(asset.id, operation_photo_file_id)

        operation = create_operation(
            type=OperationType.INCOMING.value,
            asset_id=asset.id,
            qty=qty,
            to_user_id=db_user.id,
            price=operation_price,  # Средняя цена для операции
            comment=f"Приход имущества: {data['name']}",
            photo_file_id=operation_photo_file_id
        )
        
        logger.info(f"Created operation {operation.id} for asset {asset.id} by user {db_user.id}")
        
        # Success message with prices
        instances_lines = []
        for idx, inst in enumerate(created_instances):
            price_text = f"{inst.price:.2f} руб." if inst.price is not None else "не указана"
            instances_lines.append(f"  {idx+1}. {inst.distinctive_features} - {price_text}")
        instances_list = "\n".join(instances_lines)
        
        avg_price_text = f"{operation_price:.2f} руб." if operation_price is not None else "не указана"
        
        success_text = (
            f"✅ <b>Операция успешно выполнена!</b>\n\n"
            f"📦 Имущество: <b>{data['name']}</b>\n"
            f"📊 Количество: <b>{qty}</b>\n"
            f"💰 Средняя цена: <b>{avg_price_text}</b>\n"
            f"🏷️ Код: <b>{data['code']}</b>\n"
            f"📝 Операция ID: <b>{operation.id}</b>\n"
            f"🆔 Актив ID: <b>{asset.id}</b>\n"
            f"📈 Текущее количество на складе: <b>{asset.qty}</b>\n\n"
            f"Экземпляры с ценами:\n{instances_list}"
        )
        
        # Check if message has photo (batch mode or individual mode with first photo)
        has_photo = callback.message.photo is not None and len(callback.message.photo) > 0
        
        if has_photo:
            await callback.message.edit_caption(
                caption=success_text,
                parse_mode="HTML"
            )
        else:
            await callback.message.edit_text(
                success_text,
                parse_mode="HTML"
            )
        
        await callback.answer("✅ Операция сохранена!")
        await state.clear()
        
    except Exception as e:
        logger.error(f"Error saving income operation: {e}", exc_info=True)
        await callback.answer("❌ Ошибка при сохранении операции", show_alert=True)
        
        error_text = (
            "❌ Произошла ошибка при сохранении операции.\n\n"
            "Возможные причины:\n"
            "- Проблема с базой данных\n"
            "- Несоответствие схемы БД\n\n"
            "Попробуйте начать операцию заново или обратитесь к администратору."
        )
        
        # Check if message has photo
        if callback.message.photo:
            await callback.message.edit_caption(
                caption=error_text,
                parse_mode="HTML"
            )
        else:
            await callback.message.edit_text(
                error_text,
                parse_mode="HTML"
            )
        await state.clear()


@router.callback_query(F.data == "cancel_income")
async def cancel_income(callback: CallbackQuery, state: FSMContext):
    """Cancel income operation."""
    await state.clear()
    await callback.message.edit_text("❌ Операция отменена.")
    await callback.answer("Операция отменена")


@router.message(Command("cancel"))
async def cancel_command(message: Message, state: FSMContext):
    """Cancel any ongoing operation."""
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Нет активных операций для отмены.")
        return
    
    await state.clear()
    await message.answer("✅ Операция отменена.")


@router.message(F.text == "Расход имущества")
async def expense_handler(message: Message, state: FSMContext):
    """Start outgoing operation flow."""
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
    
    # Check if there are any available assets
    available_assets = get_available_assets()
    if not available_assets:
        await message.answer(
            "❌ <b>Нет доступного имущества на складе</b>\n\n"
            "На складе нет активов с количеством больше нуля.\n"
            "Сначала выполните операцию прихода имущества.",
            parse_mode="HTML"
        )
        return
    
    # Start FSM flow
    await state.set_state(OutgoingStates.waiting_for_asset_selection)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔍 Ввести код", callback_data="outgoing_enter_code")
    builder.button(text="📋 Выбрать из списка", callback_data="outgoing_select_list")
    builder.adjust(1)
    
    await message.answer(
        "📤 <b>Расход имущества</b>\n\n"
        "Выберите способ выбора актива:",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )
    logger.info(f"User {message.from_user.id} started outgoing operation")


@router.callback_query(F.data == "outgoing_enter_code", OutgoingStates.waiting_for_asset_selection)
async def outgoing_enter_code(callback: CallbackQuery, state: FSMContext):
    """Start entering asset code."""
    await state.set_state(OutgoingStates.waiting_for_asset_code)
    await callback.message.edit_text(
        "🔍 <b>Ввод кода актива</b>\n\n"
        "Введите код (QR-код, штрихкод) актива:",
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "outgoing_select_list", OutgoingStates.waiting_for_asset_selection)
async def outgoing_select_list(callback: CallbackQuery, state: FSMContext):
    """Show list of available assets."""
    available_assets = get_available_assets()
    
    if not available_assets:
        await callback.answer("❌ Нет доступных активов", show_alert=True)
        await state.clear()
        return
    
    builder = InlineKeyboardBuilder()
    
    for asset in available_assets:
        category_name = asset.category_obj.name if asset.category_obj else "Без категории"
        code_display = f" [{asset.code}]" if asset.code else ""
        button_text = f"{asset.name}{code_display} (остаток: {int(asset.qty)})"
        # Truncate if too long
        if len(button_text) > 50:
            button_text = button_text[:47] + "..."
        builder.button(text=button_text, callback_data=f"outgoing_asset_{asset.id}")
    
    builder.adjust(1)
    
    await callback.message.edit_text(
        "📋 <b>Выбор актива</b>\n\n"
        "Выберите актив из списка:",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@router.message(OutgoingStates.waiting_for_asset_code)
async def process_asset_code(message: Message, state: FSMContext):
    """Process asset code input."""
    code = message.text.strip()
    
    if not code:
        await message.answer("❌ Код не может быть пустым. Введите код актива:")
        return
    
    asset = get_asset_by_code(code)
    
    if not asset:
        await message.answer(
            f"❌ Актив с кодом <b>{code}</b> не найден.\n\n"
            "Проверьте правильность кода или выберите актив из списка.",
            parse_mode="HTML"
        )
        return
    
    if asset.qty <= 0:
        await message.answer(
            f"❌ Актив <b>{asset.name}</b> недоступен для расхода.\n"
            f"Текущее количество на складе: {int(asset.qty)}\n\n"
            "Выберите другой актив.",
            parse_mode="HTML"
        )
        return
    
    await state.update_data(asset_id=asset.id, asset_name=asset.name, asset_qty=asset.qty)
    await state.set_state(OutgoingStates.waiting_for_recipient)
    
    # Get all users for recipient selection
    users = get_all_users()
    registered_users = [u for u in users if u.role != UserRole.UNKNOWN.value]
    
    if not registered_users:
        await message.answer(
            "❌ Нет зарегистрированных пользователей для выбора получателя.\n"
            "Операция отменена."
        )
        await state.clear()
        return
    
    builder = InlineKeyboardBuilder()
    
    for user in registered_users:
        role_text = {
            UserRole.SYSTEM_ADMIN.value: "Админ",
            UserRole.MANAGER.value: "Менеджер",
            UserRole.STOREKEEPER.value: "Кладовщик",
            UserRole.FOREMAN.value: "Прораб",
            UserRole.WORKER.value: "Рабочий"
        }.get(user.role, user.role)
        
        button_text = f"{user.fullname} ({role_text})"
        if len(button_text) > 50:
            button_text = button_text[:47] + "..."
        builder.button(text=button_text, callback_data=f"outgoing_recipient_{user.id}")
    
    builder.adjust(1)
    
    await message.answer(
        f"✅ Актив: <b>{asset.name}</b>\n"
        f"Код: <b>{asset.code or 'не указан'}</b>\n"
        f"Доступно на складе: <b>{int(asset.qty)}</b>\n\n"
        "Выберите получателя:",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )


@router.callback_query(F.data.startswith("outgoing_asset_"))
async def select_outgoing_asset(callback: CallbackQuery, state: FSMContext):
    """Select asset from list."""
    asset_id = int(callback.data.split("_")[2])
    asset = get_asset_by_id(asset_id)
    
    if not asset:
        await callback.answer("❌ Актив не найден", show_alert=True)
        return
    
    if asset.qty <= 0:
        await callback.answer("❌ Актив недоступен для расхода", show_alert=True)
        return
    
    await state.update_data(asset_id=asset.id, asset_name=asset.name, asset_qty=asset.qty)
    await state.set_state(OutgoingStates.waiting_for_recipient)
    
    # Get all users for recipient selection
    users = get_all_users()
    registered_users = [u for u in users if u.role != UserRole.UNKNOWN.value]
    
    if not registered_users:
        await callback.answer("❌ Нет зарегистрированных пользователей", show_alert=True)
        await state.clear()
        return
    
    builder = InlineKeyboardBuilder()
    
    for user in registered_users:
        role_text = {
            UserRole.SYSTEM_ADMIN.value: "Админ",
            UserRole.MANAGER.value: "Менеджер",
            UserRole.STOREKEEPER.value: "Кладовщик",
            UserRole.FOREMAN.value: "Прораб",
            UserRole.WORKER.value: "Рабочий"
        }.get(user.role, user.role)
        
        button_text = f"{user.fullname} ({role_text})"
        if len(button_text) > 50:
            button_text = button_text[:47] + "..."
        builder.button(text=button_text, callback_data=f"outgoing_recipient_{user.id}")
    
    builder.adjust(1)
    
    await callback.message.edit_text(
        f"✅ Актив: <b>{asset.name}</b>\n"
        f"Код: <b>{asset.code or 'не указан'}</b>\n"
        f"Доступно на складе: <b>{int(asset.qty)}</b>\n\n"
        "Выберите получателя:",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("outgoing_recipient_"), OutgoingStates.waiting_for_recipient)
async def select_outgoing_recipient(callback: CallbackQuery, state: FSMContext):
    """Select recipient for outgoing operation."""
    recipient_id = int(callback.data.split("_")[2])
    recipient = get_user_by_id(recipient_id)
    
    if not recipient:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return
    
    await state.update_data(recipient_id=recipient.id, recipient_name=recipient.fullname)
    await state.set_state(OutgoingStates.waiting_for_qty)
    
    data = await state.get_data()
    asset_qty = data['asset_qty']
    
    await callback.message.edit_text(
        f"✅ Получатель: <b>{recipient.fullname}</b>\n\n"
        f"Введите количество для расхода (доступно: <b>{int(asset_qty)}</b>):",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(OutgoingStates.waiting_for_qty)
async def process_outgoing_qty(message: Message, state: FSMContext):
    """Process quantity for outgoing operation."""
    try:
        qty = float(message.text.strip().replace(",", "."))
        if qty <= 0:
            raise ValueError("Quantity must be positive")
        if qty != int(qty):
            raise ValueError("Quantity must be integer")
        qty = int(qty)
    except ValueError:
        await message.answer("❌ Неверный формат количества. Введите целое число (например: 1, 5, 10):")
        return
    
    data = await state.get_data()
    asset_qty = data['asset_qty']
    
    if qty > asset_qty:
        await message.answer(
            f"❌ Недостаточно товара на складе.\n\n"
            f"Запрошено: <b>{qty}</b>\n"
            f"Доступно: <b>{int(asset_qty)}</b>\n\n"
            f"Введите количество не больше {int(asset_qty)}:",
            parse_mode="HTML"
        )
        return
    
    await state.update_data(qty=qty)
    await state.set_state(OutgoingStates.waiting_for_confirm)
    
    asset_name = data['asset_name']
    recipient_name = data['recipient_name']
    
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data="outgoing_confirm")
    builder.button(text="❌ Отменить", callback_data="outgoing_cancel")
    builder.adjust(1)
    
    await message.answer(
        "📋 <b>Подтверждение операции расхода</b>\n\n"
        f"Актив: <b>{asset_name}</b>\n"
        f"Получатель: <b>{recipient_name}</b>\n"
        f"Количество: <b>{qty}</b>\n\n"
        "Подтвердите операцию:",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )


@router.callback_query(F.data == "outgoing_confirm", OutgoingStates.waiting_for_confirm)
async def confirm_outgoing(callback: CallbackQuery, state: FSMContext):
    """Confirm and save outgoing operation."""
    data = await state.get_data()
    asset_id = data['asset_id']
    asset_name = data['asset_name']
    recipient_id = data['recipient_id']
    recipient_name = data['recipient_name']
    qty = data['qty']
    
    # Get current user (who performs the operation)
    user = callback.from_user
    if not user:
        await callback.answer("❌ Ошибка: не удалось получить информацию о пользователе", show_alert=True)
        await state.clear()
        return
    
    db_user = get_user_by_telegram_id(user.id)
    if not db_user:
        await callback.answer("❌ Ошибка: пользователь не найден в БД", show_alert=True)
        await state.clear()
        return
    
    try:
        # Get current asset to check quantity
        asset = get_asset_by_id(asset_id)
        if not asset:
            raise ValueError("Актив не найден")
        
        if asset.qty < qty:
            raise ValueError(f"Недостаточно товара на складе. Доступно: {int(asset.qty)}")
        
        # Get available instances (not assigned yet)
        available_instances = get_available_asset_instances(asset_id, limit=int(qty))
        
        if len(available_instances) < int(qty):
            raise ValueError(
                f"Недостаточно доступных экземпляров на складе. "
                f"Запрошено: {int(qty)}, доступно: {len(available_instances)}"
            )
        
        # Create operation
        operation = create_operation(
            type=OperationType.OUTGOING.value,
            asset_id=asset_id,
            qty=qty,
            from_user_id=db_user.id,  # User who performs the operation
            to_user_id=recipient_id,   # Recipient
            comment=f"Расход имущества: {asset_name}"
        )
        
        # Assign instances to recipient first
        instances_assigned = 0
        for instance in available_instances[:int(qty)]:
            update_asset_instance(
                instance_id=instance.id,
                assigned_to_user_id=recipient_id,
                state=AssetState.IN_USE.value
            )
            instances_assigned += 1
        
        logger.info(
            f"Assigned {instances_assigned} instances of asset {asset_id} to user {recipient_id}"
        )
        
        # Update asset quantity after assigning instances
        new_qty = asset.qty - qty
        updated_asset = update_asset(asset_id=asset_id, qty=new_qty)
        
        if updated_asset:
            logger.info(
                f"Updated asset {asset_id} quantity: {asset.qty} -> {new_qty}"
            )
        else:
            logger.error(f"Failed to update asset {asset_id} quantity")
        
        # Note: We don't change asset state when quantity becomes zero
        # The state remains as is (typically IN_STOCK)
        # Quantity being zero just means no items are available, not that the asset is written off
        
        success_text = (
            "✅ <b>Операция расхода успешно выполнена!</b>\n\n"
            f"Актив: <b>{asset_name}</b>\n"
            f"Получатель: <b>{recipient_name}</b>\n"
            f"Количество: <b>{qty}</b>\n"
            f"Остаток на складе: <b>{int(new_qty)}</b>"
        )
        
        # Check if message has photo
        if callback.message.photo:
            await callback.message.edit_caption(
                caption=success_text,
                parse_mode="HTML"
            )
        else:
            await callback.message.edit_text(
                success_text,
                parse_mode="HTML"
            )
        
        await callback.answer("✅ Операция сохранена")
        logger.info(
            f"Outgoing operation created: asset_id={asset_id}, qty={qty}, "
            f"from_user_id={db_user.id}, to_user_id={recipient_id}"
        )
        
        # Send notification to recipient with confirmation button
        await send_recipient_notification(
            bot=callback.bot,
            operation_id=operation.id,
            recipient_id=recipient_id,
            asset_name=asset_name,
            qty=qty,
            instances=available_instances[:int(qty)]
        )
        
    except Exception as e:
        logger.error(f"Error saving outgoing operation: {e}", exc_info=True)
        await callback.answer("❌ Ошибка при сохранении операции", show_alert=True)
        
        error_text = (
            "❌ Произошла ошибка при сохранении операции.\n\n"
            "Возможные причины:\n"
            "- Проблема с базой данных\n"
            "- Недостаточно товара на складе\n"
            "- Несоответствие схемы БД\n\n"
            "Попробуйте начать операцию заново или обратитесь к администратору."
        )
        
        # Check if message has photo; игнорируем "message is not modified" при повторном нажатии
        try:
            if callback.message.photo:
                await callback.message.edit_caption(
                    caption=error_text,
                    parse_mode="HTML"
                )
            else:
                await callback.message.edit_text(
                    error_text,
                    parse_mode="HTML"
                )
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e):
                raise

    await state.clear()


async def send_recipient_notification(
    bot: Bot,
    operation_id: int,
    recipient_id: int,
    asset_name: str,
    qty: int,
    instances: list
):
    """Send notification to recipient about received assets. Allгда отправляем отдельное сообщение с кнопкой «Имущество получил»."""
    recipient_user = get_user_by_id(recipient_id)
    if not recipient_user:
        logger.error(f"Recipient user {recipient_id} not found")
        return
    if not recipient_user.telegram_id:
        logger.error(f"Recipient user {recipient_id} has no telegram_id")
        return

    operation = get_operation_by_id(operation_id)
    if not operation:
        logger.error(f"Operation {operation_id} not found")
        return

    is_transfer = operation.type == OperationType.TRANSFER.value
    manager_link = "начальнику лично"
    if operation.from_user_id:
        from_user = get_user_by_id(operation.from_user_id)
        if from_user and from_user.telegram_id:
            manager_link = f'<a href="tg://user?id={from_user.telegram_id}">начальнику лично</a>'

    price_per_unit = None
    if operation.price is not None:
        price_per_unit = operation.price
    elif instances and len(instances) > 0 and getattr(instances[0], "price", None) is not None:
        price_per_unit = instances[0].price

    instances_text = ""
    if instances:
        instances_text = "\n".join([
            f"  • {getattr(inst, 'distinctive_features', str(inst))}" for inst in instances
        ])
    else:
        instances_text = "  —"

    price_text = ""
    if price_per_unit is not None:
        price_text = f"\n<b>Цена за единицу:</b> {price_per_unit:.2f} руб."

    if is_transfer:
        header = "📦 <b>Вам передали имущество</b> (передача от сотрудника)\n\n"
    else:
        header = "📦 <b>Вам передано имущество</b>\n\n"

    message_text = (
        f"{header}"
        f"<b>Наименование:</b> {asset_name}\n"
        f"<b>Количество:</b> {qty}{price_text}\n\n"
        f"<b>Экземпляры:</b>\n{instances_text}\n\n"
        "Вы несете ответственность за сохранность переданного имущества.\n\n"
        f"Если вы не согласны с передачей, обратитесь к {manager_link}.\n\n"
        "Подтвердите получение — нажмите кнопку ниже:"
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Имущество получил", callback_data=f"confirm_receipt_{operation_id}")
    builder.adjust(1)
    markup = builder.as_markup()

    chat_id = recipient_user.telegram_id
    try:
        photo_file_id = None
        if instances:
            for instance in instances:
                fid = getattr(instance, "photo_file_id", None)
                if fid:
                    photo_file_id = fid
                    break
        if photo_file_id:
            caption_short = (
                f"📷 {asset_name}, {qty} шт.\n\n"
                "Подробности и кнопка подтверждения — в следующем сообщении."
            )
            await bot.send_photo(
                chat_id=chat_id,
                photo=photo_file_id,
                caption=caption_short,
                parse_mode="HTML"
            )
        await bot.send_message(
            chat_id=chat_id,
            text=message_text,
            parse_mode="HTML",
            reply_markup=markup
        )
        logger.info(
            f"Sent receipt notification to recipient id={recipient_id} telegram_id={chat_id} for operation {operation_id}"
        )
    except Exception as e:
        logger.error(
            f"Failed to send notification to recipient {recipient_id} (telegram_id={chat_id}): {e}",
            exc_info=True
        )


@router.callback_query(F.data.startswith("confirm_receipt_"))
async def confirm_receipt(callback: CallbackQuery):
    """Handle recipient confirmation of asset receipt."""
    operation_id = int(callback.data.split("_")[2])
    
    user = callback.from_user
    if not user:
        await callback.answer("❌ Ошибка: не удалось получить информацию о пользователе", show_alert=True)
        return
    
    db_user = get_user_by_telegram_id(user.id)
    if not db_user:
        await callback.answer("❌ Пользователь не найден в базе данных", show_alert=True)
        return
    
    # Get operation
    operation = get_operation_by_id(operation_id)
    
    if not operation:
        await callback.answer("❌ Операция не найдена", show_alert=True)
        return
    
    # Check if user is the recipient
    if operation.to_user_id != db_user.id:
        await callback.answer("❌ Вы не являетесь получателем этого имущества", show_alert=True)
        return
    
    # Check if already signed
    if operation.signed_at:
        await callback.answer("✅ Имущество уже подтверждено", show_alert=True)
        return
    
    # Update operation with signature
    update_operation_signature(
        operation_id=operation_id,
        signed_by_user_id=db_user.id,
        auto_signed=False
    )
    
    # Update message - check if message has photo
    confirmation_text = (
        "✅ <b>Имущество подтверждено</b>\n\n"
        "Вы подтвердили получение имущества.\n"
        "Вы несете ответственность за его сохранность."
    )
    
    if callback.message.photo:
        await callback.message.edit_caption(
            caption=confirmation_text,
            parse_mode="HTML"
        )
    else:
        await callback.message.edit_text(
            text=confirmation_text,
            parse_mode="HTML"
        )
    
    await callback.answer("✅ Получение имущества подтверждено")
    logger.info(f"User {db_user.id} confirmed receipt of operation {operation_id}")


@router.callback_query(F.data == "outgoing_cancel", OutgoingStates.waiting_for_confirm)
async def cancel_outgoing(callback: CallbackQuery, state: FSMContext):
    """Cancel outgoing operation."""
    await callback.answer("Операция отменена")
    await callback.message.edit_text("❌ Операция расхода отменена.")
    await state.clear()


@router.message(F.text == "Списание имущества")
async def writeoff_handler(message: Message):
    """Handle writeoff operation."""
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
        "🗑️ <b>Списание имущества</b>\n\n"
        "Эта операция позволяет списать испорченное или утраченное имущество.\n\n"
        "Функционал в разработке...",
        parse_mode="HTML"
    )
    logger.info(f"User {message.from_user.id} started writeoff operation")


# =============================================================================
# Transfer (Передача имущества) — передача от одного пользователя другому
# =============================================================================

@router.message(F.text == "Передача имущества")
async def transfer_handler(message: Message, state: FSMContext):
    """Start transfer: show assets assigned to current user."""
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

    instances = get_asset_instances_assigned_to_user(db_user.id)
    if not instances:
        await message.answer(
            "❌ <b>У вас нет переданного имущества</b>\n\n"
            "Передавать можно только то имущество, которое уже выдано вам (операция «Расход»).",
            parse_mode="HTML"
        )
        return

    # Group by asset_id: { asset_id: (asset, count) }
    by_asset = {}
    for inst in instances:
        aid = inst.asset_id
        if aid not in by_asset:
            by_asset[aid] = [inst.asset, 0]
        by_asset[aid][1] += 1

    await state.set_state(TransferStates.waiting_for_asset)
    builder = InlineKeyboardBuilder()
    for asset_id, (asset, count) in by_asset.items():
        code_display = f" [{asset.code}]" if asset.code else ""
        button_text = f"{asset.name}{code_display} (у вас: {count})"
        if len(button_text) > 50:
            button_text = button_text[:47] + "..."
        builder.button(text=button_text, callback_data=f"transfer_asset_{asset_id}")
    builder.adjust(1)

    await message.answer(
        "🔄 <b>Передача имущества</b>\n\n"
        "Выберите актив, который хотите передать другому пользователю:",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )
    logger.info(f"User {user.id} started transfer operation")


@router.callback_query(F.data.startswith("transfer_asset_"), TransferStates.waiting_for_asset)
async def transfer_select_asset(callback: CallbackQuery, state: FSMContext):
    """Store asset, show recipient list (excluding self). answer() в начале — иначе Telegram «query is too old»."""
    try:
        await callback.answer()
    except Exception:
        pass
    asset_id = int(callback.data.split("_")[2])
    asset = get_asset_by_id(asset_id)
    if not asset:
        await callback.message.edit_text("❌ Актив не найден.")
        return

    user = callback.from_user
    db_user = get_user_by_telegram_id(user.id)
    if not db_user:
        await callback.message.edit_text("❌ Пользователь не найден.")
        await state.clear()
        return

    my_instances = get_asset_instances_assigned_to_user(db_user.id, asset_id=asset_id)
    if not my_instances:
        await callback.message.edit_text("❌ У вас нет этого актива.")
        return

    my_count = len(my_instances)
    await state.update_data(
        asset_id=asset.id,
        asset_name=asset.name,
        transfer_my_count=my_count
    )
    await state.set_state(TransferStates.waiting_for_recipient)

    users = get_all_users()
    registered = [u for u in users if u.role != UserRole.UNKNOWN.value and u.id != db_user.id]
    if not registered:
        await callback.message.edit_text(
            "❌ Нет других зарегистрированных пользователей для передачи."
        )
        await state.clear()
        return

    builder = InlineKeyboardBuilder()
    for u in registered:
        role_text = {
            UserRole.SYSTEM_ADMIN.value: "Админ",
            UserRole.MANAGER.value: "Менеджер",
            UserRole.STOREKEEPER.value: "Кладовщик",
            UserRole.FOREMAN.value: "Прораб",
            UserRole.WORKER.value: "Рабочий"
        }.get(u.role, u.role)
        btn = f"{u.fullname} ({role_text})"
        if len(btn) > 50:
            btn = btn[:47] + "..."
        builder.button(text=btn, callback_data=f"transfer_recipient_{u.id}")
    builder.adjust(1)

    await callback.message.edit_text(
        f"✅ Актив: <b>{asset.name}</b>\n"
        f"У вас: <b>{my_count}</b> шт.\n\n"
        "Выберите получателя:",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )


@router.callback_query(F.data.startswith("transfer_recipient_"), TransferStates.waiting_for_recipient)
async def transfer_select_recipient(callback: CallbackQuery, state: FSMContext):
    """Store recipient, ask for quantity. answer() в начале — иначе Telegram «query is too old»."""
    try:
        await callback.answer()
    except Exception:
        pass
    recipient_id = int(callback.data.split("_")[2])
    recipient = get_user_by_id(recipient_id)
    if not recipient:
        await callback.message.edit_text("❌ Пользователь не найден.")
        return

    await state.update_data(recipient_id=recipient.id, recipient_name=recipient.fullname)
    await state.set_state(TransferStates.waiting_for_qty)
    data = await state.get_data()
    my_count = data["transfer_my_count"]

    await callback.message.edit_text(
        f"✅ Получатель: <b>{recipient.fullname}</b>\n\n"
        f"Введите количество для передачи (от 1 до {my_count}):",
        parse_mode="HTML"
    )


@router.message(TransferStates.waiting_for_qty)
async def transfer_process_qty(message: Message, state: FSMContext):
    """Validate qty, show confirmation."""
    try:
        qty = int(message.text.strip())
        if qty < 1:
            raise ValueError("qty < 1")
    except ValueError:
        await message.answer("❌ Введите целое число (например: 1 или 2):")
        return

    data = await state.get_data()
    my_count = data["transfer_my_count"]
    if qty > my_count:
        await message.answer(
            f"❌ У вас только <b>{my_count}</b> шт. Введите число от 1 до {my_count}:",
            parse_mode="HTML"
        )
        return

    await state.update_data(qty=qty)
    await state.set_state(TransferStates.waiting_for_confirm)

    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data="transfer_confirm")
    builder.button(text="❌ Отменить", callback_data="transfer_cancel")
    builder.adjust(1)

    await message.answer(
        "📋 <b>Подтверждение передачи</b>\n\n"
        f"Актив: <b>{data['asset_name']}</b>\n"
        f"Получатель: <b>{data['recipient_name']}</b>\n"
        f"Количество: <b>{qty}</b>\n\n"
        "Подтвердите операцию:",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )


@router.callback_query(F.data == "transfer_confirm", TransferStates.waiting_for_confirm)
async def transfer_confirm(callback: CallbackQuery, state: FSMContext):
    """Reassign instances to recipient, create operation type=transfer. answer() в начале — иначе «query is too old»."""
    try:
        await callback.answer()
    except Exception:
        pass
    data = await state.get_data()
    asset_id = data["asset_id"]
    asset_name = data["asset_name"]
    recipient_id = data["recipient_id"]
    recipient_name = data["recipient_name"]
    qty = data["qty"]

    user = callback.from_user
    db_user = get_user_by_telegram_id(user.id)
    if not db_user:
        await callback.message.edit_text("❌ Пользователь не найден.")
        await state.clear()
        return

    instances = get_asset_instances_assigned_to_user(db_user.id, asset_id=asset_id, limit=int(qty))
    if len(instances) < int(qty):
        await callback.message.edit_text("❌ Недостаточно экземпляров.")
        await state.clear()
        return

    try:
        transferred_instances = instances[: int(qty)]
        for inst in transferred_instances:
            update_asset_instance(
                instance_id=inst.id,
                assigned_to_user_id=recipient_id,
                state=AssetState.IN_USE.value
            )
        operation = create_operation(
            type=OperationType.TRANSFER.value,
            asset_id=asset_id,
            qty=float(qty),
            from_user_id=db_user.id,
            to_user_id=recipient_id,
            comment=f"Передача: {asset_name}"
        )
        await callback.message.edit_text(
            "✅ <b>Передача выполнена</b>\n\n"
            f"Актив: <b>{asset_name}</b>\n"
            f"Получатель: <b>{recipient_name}</b>\n"
            f"Количество: <b>{qty}</b>\n\n"
            "Получателю отправлено уведомление. Он должен нажать «Имущество получил». "
            "Если не подтвердит и не пожалуется начальнику — через 24 часа имущество автоматически будет числиться на нём.",
            parse_mode="HTML"
        )
        logger.info(f"Transfer: user {db_user.id} -> {recipient_id}, asset_id={asset_id}, qty={qty}")

        # Уведомить получателя: сообщение + кнопка «Имущество получил»; через 24 ч — авто-подпись
        await send_recipient_notification(
            bot=callback.bot,
            operation_id=operation.id,
            recipient_id=recipient_id,
            asset_name=asset_name,
            qty=qty,
            instances=transferred_instances
        )
    except Exception as e:
        logger.error(f"Transfer error: {e}", exc_info=True)
        await callback.message.edit_text("❌ Ошибка при сохранении операции.")
    await state.clear()


@router.callback_query(F.data == "transfer_cancel", TransferStates.waiting_for_confirm)
async def transfer_cancel(callback: CallbackQuery, state: FSMContext):
    """Cancel transfer."""
    await state.clear()
    await callback.message.edit_text("❌ Передача отменена.")
    await callback.answer()


# =============================================================================
# Return (Возврат имущества) — возврат на склад
# =============================================================================

@router.message(F.text == "Возврат имущества")
async def return_handler(message: Message, state: FSMContext):
    """Start return: show assets assigned to current user."""
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

    instances = get_asset_instances_assigned_to_user(db_user.id)
    if not instances:
        await message.answer(
            "❌ <b>У вас нет имущества для возврата</b>\n\n"
            "Возвращать можно только то имущество, которое выдано вам (операция «Расход»).",
            parse_mode="HTML"
        )
        return

    by_asset = {}
    for inst in instances:
        aid = inst.asset_id
        if aid not in by_asset:
            by_asset[aid] = [inst.asset, 0]
        by_asset[aid][1] += 1

    await state.set_state(ReturnStates.waiting_for_asset)
    builder = InlineKeyboardBuilder()
    for asset_id, (asset, count) in by_asset.items():
        code_display = f" [{asset.code}]" if asset.code else ""
        button_text = f"{asset.name}{code_display} (у вас: {count})"
        if len(button_text) > 50:
            button_text = button_text[:47] + "..."
        builder.button(text=button_text, callback_data=f"return_asset_{asset_id}")
    builder.adjust(1)

    await message.answer(
        "↩️ <b>Возврат имущества на склад</b>\n\n"
        "Выберите актив, который хотите вернуть на склад:",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )
    logger.info(f"User {user.id} started return operation")


@router.callback_query(F.data.startswith("return_asset_"), ReturnStates.waiting_for_asset)
async def return_select_asset(callback: CallbackQuery, state: FSMContext):
    """Store asset, ask quantity to return. answer() в начале — иначе Telegram «query is too old»."""
    try:
        await callback.answer()
    except Exception:
        pass
    asset_id = int(callback.data.split("_")[2])
    asset = get_asset_by_id(asset_id)
    if not asset:
        await callback.message.edit_text("❌ Актив не найден.")
        return

    user = callback.from_user
    db_user = get_user_by_telegram_id(user.id)
    if not db_user:
        await callback.message.edit_text("❌ Пользователь не найден.")
        await state.clear()
        return

    my_instances = get_asset_instances_assigned_to_user(db_user.id, asset_id=asset_id)
    if not my_instances:
        await callback.message.edit_text("❌ У вас нет этого актива.")
        return

    my_count = len(my_instances)
    await state.update_data(
        asset_id=asset.id,
        asset_name=asset.name,
        return_my_count=my_count
    )
    await state.set_state(ReturnStates.waiting_for_qty)

    await callback.message.edit_text(
        f"✅ Актив: <b>{asset.name}</b>\n"
        f"У вас: <b>{my_count}</b> шт.\n\n"
        f"Введите количество для возврата на склад (от 1 до {my_count}):",
        parse_mode="HTML"
    )


@router.message(ReturnStates.waiting_for_qty)
async def return_process_qty(message: Message, state: FSMContext):
    """Validate qty, show confirmation."""
    try:
        qty = int(message.text.strip())
        if qty < 1:
            raise ValueError("qty < 1")
    except ValueError:
        await message.answer("❌ Введите целое число (например: 1 или 2):")
        return

    data = await state.get_data()
    my_count = data["return_my_count"]
    if qty > my_count:
        await message.answer(
            f"❌ У вас только <b>{my_count}</b> шт. Введите число от 1 до {my_count}:",
            parse_mode="HTML"
        )
        return

    await state.update_data(qty=qty)
    await state.set_state(ReturnStates.waiting_for_confirm)

    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить возврат", callback_data="return_confirm")
    builder.button(text="❌ Отменить", callback_data="return_cancel")
    builder.adjust(1)

    await message.answer(
        "📋 <b>Подтверждение возврата на склад</b>\n\n"
        f"Актив: <b>{data['asset_name']}</b>\n"
        f"Количество: <b>{qty}</b>\n\n"
        "Подтвердите операцию:",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )


@router.callback_query(F.data == "return_confirm", ReturnStates.waiting_for_confirm)
async def return_confirm(callback: CallbackQuery, state: FSMContext):
    """Создать запрос на возврат и отправить на подтверждение кладовщику или главному администратору."""
    try:
        await callback.answer()
    except Exception:
        pass
    data = await state.get_data()
    asset_id = data["asset_id"]
    asset_name = data["asset_name"]
    qty = data["qty"]

    user = callback.from_user
    db_user = get_user_by_telegram_id(user.id)
    if not db_user:
        await callback.message.edit_text("❌ Пользователь не найден.")
        await state.clear()
        return

    instances = get_asset_instances_assigned_to_user(db_user.id, asset_id=asset_id, limit=int(qty))
    if len(instances) < int(qty):
        await callback.message.edit_text("❌ Недостаточно экземпляров.")
        await state.clear()
        return

    approver = get_return_approver()
    if not approver:
        await callback.message.edit_text(
            "❌ В системе нет назначенного кладовщика или главного администратора. "
            "Обратитесь к администратору для настройки прав."
        )
        await state.clear()
        return

    try:
        pending = create_pending_return(
            from_user_id=db_user.id,
            asset_id=asset_id,
            asset_name=asset_name,
            qty=float(qty)
        )
    except Exception as e:
        logger.exception("create_pending_return: %s", e)
        await callback.message.edit_text("❌ Ошибка при создании запроса. Попробуйте позже.")
        await state.clear()
        return

    approver_role = "Кладовщик" if approver.role == UserRole.STOREKEEPER.value else "Главный администратор"
    text_to_approver = (
        "↩️ <b>Запрос на возврат на склад</b>\n\n"
        f"<b>От кого:</b> {db_user.fullname}\n"
        f"<b>Актив:</b> {asset_name}\n"
        f"<b>Количество:</b> {int(qty)}\n\n"
        f"Подтвердите или отклоните возврат (вы — {approver_role}):"
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить возврат", callback_data=f"approve_return_{pending.id}")
    builder.button(text="❌ Отклонить", callback_data=f"reject_return_{pending.id}")
    builder.adjust(1)

    try:
        await callback.bot.send_message(
            chat_id=approver.telegram_id,
            text=text_to_approver,
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        logger.exception("Notify approver: %s", e)
        await callback.message.edit_text(
            "❌ Не удалось отправить запрос подтверждающему. Попробуйте позже."
        )
        await state.clear()
        return

    await callback.message.edit_text(
        "⏳ <b>Запрос на возврат отправлен</b>\n\n"
        f"<b>Актив:</b> {asset_name}\n"
        f"<b>Количество:</b> {qty}\n\n"
        "Ожидайте подтверждения кладовщика или главного администратора.\n"
        "Вам придёт уведомление после решения.",
        parse_mode="HTML"
    )
    await state.clear()
    logger.info(f"Return request {pending.id} from user {db_user.id} sent to approver {approver.id}")


@router.callback_query(F.data == "return_cancel", ReturnStates.waiting_for_confirm)
async def return_cancel(callback: CallbackQuery, state: FSMContext):
    """Cancel return."""
    await state.clear()
    await callback.message.edit_text("❌ Возврат отменён.")
    await callback.answer()


def _can_approve_return(user_role: str) -> bool:
    """Право подтверждать возврат: кладовщик или системный администратор."""
    return user_role in (UserRole.STOREKEEPER.value, UserRole.SYSTEM_ADMIN.value)


def _do_approve_return(pending, db_user_id: int, from_user, message_edit_func, bot, photo_file_id: str = None) -> bool:
    """Выполнить подтверждение возврата: экземпляры, qty, операция, статус. Возвращает True при успехе."""
    pending_id = pending.id
    instances = get_asset_instances_assigned_to_user(pending.from_user_id, asset_id=pending.asset_id, limit=int(pending.qty))
    if len(instances) < int(pending.qty):
        update_pending_return_status(pending_id, "rejected", db_user_id)
        return False
    asset = get_asset_by_id(pending.asset_id)
    if not asset:
        return False
    if photo_file_id:
        add_asset_return_photo(pending.asset_id, photo_file_id)
    for inst in instances[: int(pending.qty)]:
        update_asset_instance(
            instance_id=inst.id,
            assigned_to_user_id=None,
            state=AssetState.IN_STOCK.value
        )
    new_qty = asset.qty + int(pending.qty)
    update_asset(asset_id=pending.asset_id, qty=new_qty)
    create_operation(
        type=OperationType.RETURN.value,
        asset_id=pending.asset_id,
        qty=pending.qty,
        from_user_id=pending.from_user_id,
        to_user_id=None,
        comment=f"Возврат на склад: {pending.asset_name} (подтверждён кладовщиком/админом)"
    )
    update_pending_return_status(pending_id, "approved", db_user_id)
    return True


@router.callback_query(F.data.startswith("approve_return_"))
async def approve_return_callback(callback: CallbackQuery, state: FSMContext):
    """Подтверждение возврата кладовщиком (с фото) или главным администратором (без фото)."""
    try:
        await callback.answer()
    except Exception:
        pass
    pending_id = int(callback.data.split("_")[2])
    pending = get_pending_return_by_id(pending_id)
    if not pending:
        await callback.message.edit_text("❌ Запрос не найден или уже обработан.")
        return
    if pending.status != "pending":
        await callback.message.edit_text("❌ Этот запрос уже обработан.")
        return

    db_user = get_user_by_telegram_id(callback.from_user.id)
    if not db_user or not _can_approve_return(db_user.role):
        await callback.message.edit_text("❌ У вас нет прав подтверждать возврат на склад.")
        return

    approver = get_return_approver()
    if not approver or approver.id != db_user.id:
        await callback.message.edit_text("❌ Подтверждать может только назначенный кладовщик или главный администратор.")
        return

    from_user = get_user_by_id(pending.from_user_id)
    instances = get_asset_instances_assigned_to_user(pending.from_user_id, asset_id=pending.asset_id, limit=int(pending.qty))
    if len(instances) < int(pending.qty):
        update_pending_return_status(pending_id, "rejected", db_user.id)
        await callback.message.edit_text(
            "❌ Отклонено: у пользователя недостаточно экземпляров для возврата (возможно, часть уже передана)."
        )
        if from_user:
            try:
                await callback.bot.send_message(
                    from_user.telegram_id,
                    "↩️ <b>Возврат на склад отклонён</b>\n\n"
                    f"Недостаточно экземпляров.\n<b>Актив:</b> {pending.asset_name}",
                    parse_mode="HTML"
                )
            except Exception:
                pass
        return

    # Кладовщик обязан прислать фото перед подтверждением; главный администратор — нет
    if db_user.role == UserRole.STOREKEEPER.value:
        await callback.message.edit_text(
            "📷 <b>Подтверждение возврата</b>\n\nОтправьте фото товара для привязки к возврату.",
            parse_mode="HTML"
        )
        await state.set_state(ReturnStates.waiting_for_storekeeper_photo)
        await state.update_data(pending_return_id=pending_id)
        return

    # Главный администратор — подтверждаем сразу без фото
    try:
        ok = _do_approve_return(pending, db_user.id, from_user, callback.message.edit_text, callback.bot, photo_file_id=None)
        if not ok:
            await callback.message.edit_text("❌ Ошибка при выполнении возврата.")
            return
    except Exception as e:
        logger.exception("approve_return: %s", e)
        await callback.message.edit_text("❌ Ошибка при выполнении возврата.")
        return

    await callback.message.edit_text(
        "✅ <b>Возврат на склад подтверждён</b>\n\n"
        f"<b>Актив:</b> {pending.asset_name}\n"
        f"<b>Количество:</b> {int(pending.qty)}\n"
        f"<b>От пользователя:</b> {from_user.fullname if from_user else '?'}",
        parse_mode="HTML"
    )
    if from_user:
        try:
            await callback.bot.send_message(
                from_user.telegram_id,
                "✅ <b>Возврат на склад подтверждён</b>\n\n"
                f"<b>Актив:</b> {pending.asset_name}\n"
                f"<b>Количество:</b> {int(pending.qty)}",
                parse_mode="HTML"
            )
        except Exception:
            pass
    logger.info(f"Return approved: pending_id={pending_id}, approver={db_user.id}")


@router.message(ReturnStates.waiting_for_storekeeper_photo, F.photo)
async def storekeeper_return_photo_handler(message: Message, state: FSMContext):
    """Приём фото от кладовщика и подтверждение возврата на склад."""
    db_user = get_user_by_telegram_id(message.from_user.id)
    if not db_user or db_user.role != UserRole.STOREKEEPER.value:
        await state.clear()
        await message.answer("❌ У вас нет прав. Ожидалось фото от кладовщика.")
        return
    approver = get_return_approver()
    if not approver or approver.id != db_user.id:
        await state.clear()
        await message.answer("❌ Подтверждать возврат может только назначенный кладовщик.")
        return

    data = await state.get_data()
    pending_id = data.get("pending_return_id")
    if not pending_id:
        await state.clear()
        await message.answer("❌ Сессия истекла. Начните подтверждение возврата заново.")
        return

    pending = get_pending_return_by_id(pending_id)
    if not pending or pending.status != "pending":
        await state.clear()
        await message.answer("❌ Запрос не найден или уже обработан.")
        return

    photo_file_id = message.photo[-1].file_id
    from_user = get_user_by_id(pending.from_user_id)

    try:
        ok = _do_approve_return(pending, db_user.id, from_user, None, message.bot, photo_file_id=photo_file_id)
        await state.clear()
        if not ok:
            await message.answer("❌ Ошибка при выполнении возврата.")
            return
    except Exception as e:
        logger.exception("storekeeper_return_photo: %s", e)
        await state.clear()
        await message.answer("❌ Ошибка при выполнении возврата.")
        return

    await message.answer(
        "✅ <b>Возврат на склад подтверждён</b>\n\n"
        f"<b>Актив:</b> {pending.asset_name}\n"
        f"<b>Количество:</b> {int(pending.qty)}\n"
        f"<b>От пользователя:</b> {from_user.fullname if from_user else '?'}",
        parse_mode="HTML"
    )
    if from_user:
        try:
            await message.bot.send_message(
                from_user.telegram_id,
                "✅ <b>Возврат на склад подтверждён</b>\n\n"
                f"<b>Актив:</b> {pending.asset_name}\n"
                f"<b>Количество:</b> {int(pending.qty)}",
                parse_mode="HTML"
            )
        except Exception:
            pass
    logger.info(f"Return approved with photo: pending_id={pending_id}, approver={db_user.id}")


@router.callback_query(F.data.startswith("reject_return_"))
async def reject_return_callback(callback: CallbackQuery):
    """Отклонение возврата кладовщиком или главным администратором."""
    try:
        await callback.answer()
    except Exception:
        pass
    pending_id = int(callback.data.split("_")[2])
    pending = get_pending_return_by_id(pending_id)
    if not pending:
        await callback.message.edit_text("❌ Запрос не найден или уже обработан.")
        return
    if pending.status != "pending":
        await callback.message.edit_text("❌ Этот запрос уже обработан.")
        return

    db_user = get_user_by_telegram_id(callback.from_user.id)
    if not db_user or not _can_approve_return(db_user.role):
        await callback.message.edit_text("❌ У вас нет прав отклонять возврат на склад.")
        return

    approver = get_return_approver()
    if not approver or approver.id != db_user.id:
        await callback.message.edit_text("❌ Отклонять может только назначенный кладовщик или главный администратор.")
        return

    update_pending_return_status(pending_id, "rejected", db_user.id)
    from_user = get_user_by_id(pending.from_user_id)

    await callback.message.edit_text(
        "❌ <b>Возврат на склад отклонён</b>\n\n"
        f"<b>Актив:</b> {pending.asset_name}\n"
        f"<b>Количество:</b> {int(pending.qty)}",
        parse_mode="HTML"
    )
    if from_user:
        try:
            await callback.bot.send_message(
                from_user.telegram_id,
                "↩️ <b>Возврат на склад отклонён</b>\n\n"
                f"<b>Актив:</b> {pending.asset_name}\n"
                f"<b>Количество:</b> {int(pending.qty)}\n\n"
                "Запрос отклонил кладовщик или администратор.",
                parse_mode="HTML"
            )
        except Exception:
            pass
    logger.info(f"Return rejected: pending_id={pending_id}, by={db_user.id}")
