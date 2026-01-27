#!/usr/bin/env python3
"""Script to display warehouse data from database in table format."""
import sys
import os
import logging
import warnings

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
        
        # Table header
        print("\n" + "=" * 120)
        print("СОСТОЯНИЕ СКЛАДА".center(120))
        print("=" * 120)
        print()
        print(f"{'№':<4} │ {'Название':<{max_name_len}} │ {'Категория':<15} │ {'Код':<15} │ {'Всего':<8} │ {'На складе':<12} │ {'Назначено':<12} │ {'Последняя цена':<15}")
        print("─" * 120)
        
        total_qty = 0
        total_in_stock = 0
        total_assigned = 0
        
        # Get operations to find last incoming price
        from src.services.db import Operation
        for idx, (asset, category) in enumerate(assets_data, 1):
            category_name = category.name if category else "-"
            code = asset.code or "-"
            
            # Get instances directly from session
            from src.services.db import AssetInstance
            instances = session.query(AssetInstance).filter(AssetInstance.asset_id == asset.id).all()
            in_stock = sum(1 for inst in instances if inst.state == AssetState.IN_STOCK.value)
            assigned = sum(1 for inst in instances if inst.assigned_to_user_id is not None)
            
            # Get last incoming operation price
            last_incoming = session.query(Operation).filter(
                Operation.asset_id == asset.id,
                Operation.type == OperationType.INCOMING.value
            ).order_by(Operation.timestamp.desc()).first()
            
            last_price = "-"
            if last_incoming and last_incoming.price is not None:
                last_price = f"{last_incoming.price:.2f} руб."
            
            total_qty += len(instances) if instances else int(asset.qty)
            total_in_stock += in_stock
            total_assigned += assigned
            
            # Print row
            print(f"{idx:<4} │ {asset.name:<{max_name_len}} │ {category_name:<15} │ {code:<15} │ "
                  f"{len(instances) if instances else int(asset.qty):<8} │ {in_stock:<12} │ {assigned:<12} │ {last_price:<15}")
        
        # Print totals
        print("─" * 120)
        print(f"{'ИТОГО':<4} │ {'':<{max_name_len}} │ {'':<15} │ {'':<15} │ "
              f"{total_qty:<8} │ {total_in_stock:<12} │ {total_assigned:<12} │ {'':<15}")
        print()
        
    finally:
        session.close()
        logging.getLogger('sqlalchemy.engine').disabled = False


def print_incoming_operations():
    """Print incoming operations with prices for control."""
    from src.services.db import Operation, Asset
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from src.config import Config
    
    # Create a new engine without echo
    db_url = f"sqlite:///{Config.DB_PATH}"
    engine = create_engine(
        db_url,
        echo=False,
        connect_args={"check_same_thread": False}
    )
    
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        # Get all incoming operations ordered by timestamp desc
        operations = session.query(Operation, Asset).join(
            Asset, Operation.asset_id == Asset.id
        ).filter(
            Operation.type == OperationType.INCOMING.value
        ).order_by(Operation.timestamp.desc()).limit(20).all()
        
        if not operations:
            return
        
        print("=" * 120)
        print("ОПЕРАЦИИ ПРИХОДА (последние 20)".center(120))
        print("=" * 120)
        print()
        print(f"{'№':<4} │ {'Дата':<19} │ {'Товар':<30} │ {'Код':<15} │ {'Кол-во':<8} │ {'Цена за ед.':<15} │ {'Сумма':<15}")
        print("─" * 120)
        
        for idx, (op, asset) in enumerate(operations, 1):
            date_str = op.timestamp.strftime('%Y-%m-%d %H:%M')
            price_str = f"{op.price:.2f} руб." if op.price is not None else "-"
            total_str = f"{op.price * op.qty:.2f} руб." if op.price is not None else "-"
            
            print(f"{idx:<4} │ {date_str:<19} │ {asset.name[:29]:<30} │ {asset.code or '-':<15} │ "
                  f"{op.qty:<8} │ {price_str:<15} │ {total_str:<15}")
        
        print("─" * 120)
        
        # Calculate totals
        total_qty = sum(op.qty for op, _ in operations)
        operations_with_price = [(op, asset) for op, asset in operations if op.price is not None]
        total_sum = sum(op.price * op.qty for op, _ in operations_with_price)
        
        print(f"{'ИТОГО':<4} │ {'':<19} │ {'':<30} │ {'':<15} │ "
              f"{total_qty:<8} │ {'':<15} │ {f'{total_sum:.2f} руб.' if operations_with_price else '-':<15}")
        print()
        
    finally:
        session.close()


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
        
        # Print incoming operations with prices
        print_incoming_operations()
        
        print("=" * 120)
    except Exception as e:
        sys.stderr = old_stderr
        print(f"Ошибка: {e}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
