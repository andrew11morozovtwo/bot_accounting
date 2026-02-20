#!/usr/bin/env python3
"""Script to display warehouse data from database in table format."""
import sys
import os
import io
import logging
import warnings

# Windows: UTF-8 для консоли, чтобы русский и символы таблицы отображались
if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

# Suppress all warnings and logging
warnings.filterwarnings('ignore')
logging.basicConfig(level=logging.CRITICAL + 1)  # Set to level above CRITICAL
logging.getLogger().setLevel(logging.CRITICAL + 1)
logging.getLogger('sqlalchemy.engine').setLevel(logging.CRITICAL + 1)
logging.getLogger('sqlalchemy').setLevel(logging.CRITICAL + 1)
logging.getLogger('sqlalchemy.engine.base').setLevel(logging.CRITICAL + 1)
logging.getLogger('sqlalchemy.pool').setLevel(logging.CRITICAL + 1)

# Disable SQLAlchemy echo before importing
os.environ['SQLALCHEMY_ECHO'] = 'False'

# Add parent directory to path to import src modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Temporarily disable DEV_MODE to prevent SQL logging
from src.config import Config
_original_dev_mode = Config.DEV_MODE
Config.DEV_MODE = False

from src.services.db import (
    init_db,
    get_all_categories,
    get_asset_instances_by_asset_id,
    get_user_by_id,
    AssetState,
    OperationType
)
from sqlalchemy.orm import Session

# Restore original DEV_MODE after import
Config.DEV_MODE = _original_dev_mode


def get_all_assets_with_category(session):
    """Get all assets with their categories."""
    from src.services.db import Asset, Category
    return session.query(Asset, Category).outerjoin(
        Category, Asset.category_id == Category.id
    ).order_by(Asset.name).all()


def print_warehouse_table():
    """Print warehouse data in table format."""
    from src.services.db import Asset, Category, AssetInstance
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from src.config import Config
    
    # Create a new engine without echo
    db_url = f"sqlite:///{Config.DB_PATH}"
    engine = create_engine(
        db_url,
        echo=False,  # Disable SQL logging
        connect_args={"check_same_thread": False}
    )
    
    # Create session from this engine
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        assets_data = get_all_assets_with_category(session)
        
        if not assets_data:
            print("\n" + "=" * 100)
            print("СОСТОЯНИЕ СКЛАДА".center(100))
            print("=" * 100)
            print("\n  Склад пуст\n")
            return
        
        # Calculate column widths
        max_name_len = max(len(asset.name) for asset, _ in assets_data)
        max_name_len = max(max_name_len, 20)
        
        # Table header: Код и Всего убраны; Цена уже; добавлены Фото (приход) и Фото возврат
        col_price = 10   # узкий столбец "Цена"
        col_photo = 6    # Фото приход (есть/—)
        col_return_photo = 14  # Фото при возврате (количество)
        total_width = 4 + 3 + max_name_len + 3 + 15 + 3 + 12 + 3 + 12 + 3 + col_price + 3 + col_photo + 3 + col_return_photo
        print("\n" + "=" * total_width)
        print("СОСТОЯНИЕ СКЛАДА".center(total_width))
        print("=" * total_width)
        print()
        print(f"{'No':<4} | {'Название':<{max_name_len}} | {'Категория':<15} | {'На складе':<12} | {'Назначено':<12} | {'Цена':<{col_price}} | {'Фото':<{col_photo}} | {'Фото возврат':<{col_return_photo}}")
        print("-" * total_width)
        
        total_in_stock = 0
        total_assigned = 0
        
        from src.services.db import Operation, AssetInstance, AssetReturnPhoto
        for idx, (asset, category) in enumerate(assets_data, 1):
            category_name = category.name if category else "-"
            
            instances = session.query(AssetInstance).filter(AssetInstance.asset_id == asset.id).all()
            in_stock = sum(1 for inst in instances
                          if inst.state == AssetState.IN_STOCK.value
                          and inst.assigned_to_user_id is None)
            assigned = sum(1 for inst in instances if inst.assigned_to_user_id is not None)
            
            last_incoming = session.query(Operation).filter(
                Operation.asset_id == asset.id,
                Operation.type == OperationType.INCOMING.value
            ).order_by(Operation.timestamp.desc()).first()
            last_price = "-"
            if last_incoming and last_incoming.price is not None:
                last_price = f"{last_incoming.price:.2f}"
            if len(last_price) > col_price:
                last_price = last_price[: col_price - 1] + "…"
            
            # Фото при приходе: в БД хранится file_id, имени файла нет — показываем наличие
            photo_income = "есть" if (getattr(asset, 'first_income_photo_file_id', None)) else "—"
            return_photos_count = session.query(AssetReturnPhoto).filter(
                AssetReturnPhoto.asset_id == asset.id
            ).count()
            photo_return_str = str(return_photos_count)
            
            total_in_stock += in_stock
            total_assigned += assigned
            
            print(f"{idx:<4} | {asset.name:<{max_name_len}} | {category_name:<15} | {in_stock:<12} | {assigned:<12} | {last_price:<{col_price}} | {photo_income:<{col_photo}} | {photo_return_str:<{col_return_photo}}")
        
        print("-" * total_width)
        print(f"{'ИТОГО':<4} | {'':<{max_name_len}} | {'':<15} | {total_in_stock:<12} | {total_assigned:<12} | {'':<{col_price}} | {'':<{col_photo}} | {'':<{col_return_photo}}")
        print()
        
    finally:
        session.close()
        logging.getLogger('sqlalchemy.engine').disabled = False


def main():
    """Main function."""
    # Suppress SQLAlchemy logging during init
    import logging
    import sys
    from io import StringIO
    
    # Redirect stderr to suppress SQLAlchemy logs
    old_stderr = sys.stderr
    sys.stderr = StringIO()
    
    try:
        # Initialize database (ensures tables exist)
        # Temporarily disable DEV_MODE
        Config.DEV_MODE = False
        init_db()
        Config.DEV_MODE = _original_dev_mode
        
        # Restore stderr
        sys.stderr = old_stderr
        
        print_warehouse_table()
        print("=" * 120)
    except Exception as e:
        sys.stderr = old_stderr
        print(f"Ошибка: {e}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
