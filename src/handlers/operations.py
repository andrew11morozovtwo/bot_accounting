"""Operations handlers."""
import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.services.db import (
    get_user_by_telegram_id,
    UserRole,
    create_asset,
    get_asset_by_code,
    update_asset,
    create_operation,
    OperationType,
    AssetState,
    get_all_categories,
    get_category_by_id,
    get_category_by_name,
    create_category,
    create_asset_instance,
    get_next_instance_number
)
from src.states.income import IncomeStates

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
async def process_batch_photo(message: Message, state: FSMContext):
    """Process batch photo (one photo for all instances)."""
    photo_file_id = message.photo[-1].file_id  # Get highest resolution photo
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


@router.message(IncomeStates.waiting_for_batch_photo)
async def process_batch_photo_text(message: Message, state: FSMContext):
    """Handle text when batch photo expected."""
    await message.answer(
        "❌ Пожалуйста, отправьте фото или нажмите 'Пропустить'."
    )


@router.message(IncomeStates.waiting_for_instance_photo, F.photo)
async def process_instance_photo(message: Message, state: FSMContext):
    """Process photo for individual instance."""
    data = await state.get_data()
    instances = data.get('instances', [])
    current_index = data.get('current_instance_index', 0)
    
    photo_file_id = message.photo[-1].file_id
    
    # Initialize instance_photos dict if not exists
    if 'instance_photos' not in data:
        data['instance_photos'] = {}
    
    instance_photos = data['instance_photos']
    instance_photos[current_index] = photo_file_id
    await state.update_data(instance_photos=instance_photos)
    
    # Move to price input for this instance
    await state.set_state(IncomeStates.waiting_for_instance_price)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="⏭️ Пропустить цену", callback_data="skip_instance_price")
    
    await message.answer(
        f"✅ Фото для экземпляра #{current_index + 1}: <b>{instances[current_index]}</b>\n\n"
        "Введите учетную цену для этого экземпляра в рублях (например: 1500.50):",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )


@router.message(IncomeStates.waiting_for_instance_price)
async def process_instance_price(message: Message, state: FSMContext):
    """Process price input for individual instance."""
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
    """Handle text when instance photo expected."""
    await message.answer(
        "❌ Пожалуйста, отправьте фото или нажмите 'Пропустить для этого экземпляра'."
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
async def expense_handler(message: Message):
    """Handle expense operation."""
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
        "📤 <b>Расход имущества</b>\n\n"
        "Эта операция позволяет зарегистрировать выдачу имущества со склада.\n\n"
        "Функционал в разработке...",
        parse_mode="HTML"
    )
    logger.info(f"User {message.from_user.id} started expense operation")


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


@router.message(F.text == "Передача имущества")
async def transfer_handler(message: Message):
    """Handle transfer operation."""
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
        "🔄 <b>Передача имущества</b>\n\n"
        "Эта операция позволяет передать имущество между подразделениями или сотрудниками.\n\n"
        "Функционал в разработке...",
        parse_mode="HTML"
    )
    logger.info(f"User {message.from_user.id} started transfer operation")


@router.message(F.text == "Возврат имущества")
async def return_handler(message: Message):
    """Handle return operation."""
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
        "↩️ <b>Возврат имущества</b>\n\n"
        "Эта операция позволяет зарегистрировать возврат имущества на склад.\n\n"
        "Функционал в разработке...",
        parse_mode="HTML"
    )
    logger.info(f"User {message.from_user.id} started return operation")
