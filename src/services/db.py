"""Database models and schema definitions."""
import logging
from enum import Enum
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Float,
    ForeignKey,
    DateTime,
    Text,
    Boolean,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker, Session
from sqlalchemy.sql import func

from src.config import Config

logger = logging.getLogger(__name__)

Base = declarative_base()


# ============================================================================
# Enums and Constants
# ============================================================================

class UserRole(str, Enum):
    """User roles in the system."""
    SYSTEM_ADMIN = "system_admin"
    MANAGER = "manager"
    STOREKEEPER = "storekeeper"
    FOREMAN = "foreman"
    WORKER = "worker"
    UNKNOWN = "unknown"  # Default for unregistered users


class UserStatus(str, Enum):
    """User account status."""
    ACTIVE = "active"
    BLOCKED = "blocked"


class AssetState(str, Enum):
    """Asset state."""
    IN_USE = "in_use"
    IN_STOCK = "in_stock"
    WRITTEN_OFF = "written_off"
    LOST = "lost"
    RESERVED = "reserved"  # Optional: for reserved assets


class OperationType(str, Enum):
    """Operation types."""
    INCOMING = "incoming"  # Поступление
    OUTGOING = "outgoing"  # Выдача
    WRITEOFF = "writeoff"  # Списание
    INVENTORY = "inventory"  # Инвентаризация
    TRANSFER = "transfer"  # Передача
    RETURN = "return"  # Возврат


# ============================================================================
# Database Models
# ============================================================================

class User(Base):
    """
    User table.
    
    Fields:
        id: Primary key
        telegram_id: Telegram user ID (unique)
        fullname: User's full name or alias
        role: User role (UserRole enum)
        status: User account status (UserStatus enum)
        created_at: Account creation timestamp
        updated_at: Last update timestamp
    """
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    fullname = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default=UserRole.UNKNOWN.value)
    status = Column(String(20), nullable=False, default=UserStatus.ACTIVE.value)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    owned_assets = relationship("Asset", back_populates="owner", foreign_keys="Asset.owner_user_id")
    operations_from = relationship("Operation", back_populates="from_user", foreign_keys="Operation.from_user_id")
    operations_to = relationship("Operation", back_populates="to_user", foreign_keys="Operation.to_user_id")
    log_entries = relationship("LogEntry", back_populates="user")


class Category(Base):
    """
    Category table for asset categorization.
    
    Fields:
        id: Primary key
        name: Category name (unique)
        created_at: Creation timestamp
    """
    __tablename__ = "categories"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    
    # Relationships
    assets = relationship("Asset", back_populates="category_obj")


class Asset(Base):
    """
    Asset (Material values) table.
    
    Fields:
        id: Primary key
        name: Asset name
        category_id: Foreign key to Category
        code: QR/barcode/unique code
        owner_user_id: Foreign key to User (current owner)
        qty: Quantity
        price: Price per unit (nullable)
        state: Asset state (AssetState enum)
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """
    __tablename__ = "assets"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    code = Column(String(100), unique=True, nullable=True, index=True)  # QR/barcode
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    qty = Column(Float, nullable=False, default=0.0)
    price = Column(Float, nullable=True)  # Price per unit
    state = Column(String(50), nullable=False, default=AssetState.IN_STOCK.value)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    owner = relationship("User", back_populates="owned_assets", foreign_keys=[owner_user_id])
    category_obj = relationship("Category", back_populates="assets")
    operations = relationship("Operation", back_populates="asset")
    instances = relationship("AssetInstance", back_populates="asset", cascade="all, delete-orphan")


class AssetInstance(Base):
    """
    Asset instance table for individual items.
    
    Fields:
        id: Primary key
        asset_id: Foreign key to Asset
        distinctive_features: Distinctive features or auto-generated number (e.g., "синий", "Экз. #1")
        assigned_to_user_id: Foreign key to User (nullable, for assigned instances)
        photo_file_id: Telegram file_id for instance photo (nullable)
        price: Price per unit for this instance (nullable)
        state: Instance state (in_stock, assigned, etc.)
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """
    __tablename__ = "asset_instances"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    distinctive_features = Column(String(255), nullable=False)  # "синий", "красный", "Экз. #1"
    assigned_to_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    photo_file_id = Column(String(255), nullable=True)  # Telegram file_id (optional)
    price = Column(Float, nullable=True)  # Price per unit for this instance
    state = Column(String(50), nullable=False, default=AssetState.IN_STOCK.value)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    asset = relationship("Asset", back_populates="instances")
    assigned_to_user = relationship("User", foreign_keys=[assigned_to_user_id])


class Operation(Base):
    """
    Operation table.
    
    Fields:
        id: Primary key
        type: Operation type (OperationType enum)
        asset_id: Foreign key to Asset
        from_user_id: Foreign key to User (source user, nullable)
        to_user_id: Foreign key to User (destination user, nullable)
        qty: Quantity involved in operation
        price: Price per unit for this operation (nullable, for incoming operations)
        timestamp: Operation timestamp
        comment: Comment or reason for operation
        photo_file_id: Telegram file_id (optional)
    """
    __tablename__ = "operations"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String(50), nullable=False)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False)
    from_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    to_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    qty = Column(Float, nullable=False)
    price = Column(Float, nullable=True)  # Price per unit for this operation
    timestamp = Column(DateTime, nullable=False, server_default=func.now())
    comment = Column(Text, nullable=True)
    photo_file_id = Column(String(255), nullable=True)  # Telegram file_id (optional)
    
    # Relationships
    asset = relationship("Asset", back_populates="operations")
    from_user = relationship("User", back_populates="operations_from", foreign_keys=[from_user_id])
    to_user = relationship("User", back_populates="operations_to", foreign_keys=[to_user_id])


class LogEntry(Base):
    """
    Log entry table (optional, for audit logging).
    
    Fields:
        id: Primary key
        user_id: Foreign key to User (nullable, for system actions)
        action: Action description
        details: Additional details (JSON/text)
        created_at: Log entry timestamp
    """
    __tablename__ = "log_entries"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(255), nullable=False)
    details = Column(Text, nullable=True)  # JSON or text
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    
    # Relationships
    user = relationship("User", back_populates="log_entries")


# ============================================================================
# Database Initialization
# ============================================================================

def get_db_engine():
    """Create and return database engine."""
    db_url = f"sqlite:///{Config.DB_PATH}"
    engine = create_engine(
        db_url,
        echo=Config.DEV_MODE,  # Log SQL queries in dev mode
        connect_args={"check_same_thread": False}  # For SQLite async compatibility
    )
    return engine


def init_db():
    """Initialize database: create all tables and seed default categories."""
    engine = get_db_engine()
    Base.metadata.create_all(engine)
    
    # Seed default categories
    session = get_session()
    try:
        default_categories = ["Мебель", "Инструмент", "Приборы"]
        for cat_name in default_categories:
            existing = session.query(Category).filter(Category.name == cat_name).first()
            if not existing:
                category = Category(name=cat_name)
                session.add(category)
        session.commit()
    except Exception as e:
        session.rollback()
        raise
    finally:
        session.close()
    
    # Migrate assets table if needed (category -> category_id)
    _migrate_assets_table(engine)
    
    # Migrate asset_instances table if needed (add photo_file_id)
    _migrate_asset_instances_table(engine)
    
    # Migrate operations table if needed (add price)
    _migrate_operations_table(engine)
    
    return engine


def _migrate_assets_table(engine):
    """Migrate assets table from category (string) to category_id (FK) if needed."""
    import sqlite3
    from sqlalchemy import inspect
    
    db_path = Config.DB_PATH
    
    # Check if migration is needed
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    
    if 'assets' not in table_names:
        # Table doesn't exist yet, no migration needed
        return
    
    columns = [col['name'] for col in inspector.get_columns('assets')]
    
    has_old_column = 'category' in columns
    has_new_column = 'category_id' in columns
    
    if has_new_column or not has_old_column:
        # Migration not needed or already done
        return
    
    # Migration needed
    logger.info("Migrating assets table: category -> category_id")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Get category mapping
        session = get_session()
        try:
            categories = session.query(Category).all()
            category_map = {cat.name: cat.id for cat in categories}
        finally:
            session.close()
        
        # Create new table
        cursor.execute("""
            CREATE TABLE assets_new (
                id INTEGER NOT NULL,
                name VARCHAR(255) NOT NULL,
                category_id INTEGER,
                code VARCHAR(100),
                owner_user_id INTEGER,
                qty FLOAT NOT NULL DEFAULT 0.0,
                price FLOAT,
                state VARCHAR(50) NOT NULL DEFAULT 'in_stock',
                created_at DATETIME NOT NULL DEFAULT (CURRENT_TIMESTAMP),
                updated_at DATETIME NOT NULL DEFAULT (CURRENT_TIMESTAMP),
                PRIMARY KEY (id),
                FOREIGN KEY(category_id) REFERENCES categories (id),
                FOREIGN KEY(owner_user_id) REFERENCES users (id),
                UNIQUE (code)
            )
        """)
        
        # Copy data
        cursor.execute("SELECT * FROM assets")
        old_assets = cursor.fetchall()
        cursor.execute("PRAGMA table_info(assets)")
        old_columns = [row[1] for row in cursor.fetchall()]
        
        for old_row in old_assets:
            asset_dict = dict(zip(old_columns, old_row))
            category_id = None
            if asset_dict.get('category'):
                category_name = asset_dict['category']
                category_id = category_map.get(category_name)
            
            cursor.execute("""
                INSERT INTO assets_new (
                    id, name, category_id, code, owner_user_id, qty, price, state, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                asset_dict['id'],
                asset_dict['name'],
                category_id,
                asset_dict.get('code'),
                asset_dict.get('owner_user_id'),
                asset_dict.get('qty', 0.0),
                asset_dict.get('price'),
                asset_dict.get('state', 'in_stock'),
                asset_dict.get('created_at'),
                asset_dict.get('updated_at')
            ))
        
        # Drop old table and rename new
        cursor.execute("DROP TABLE assets")
        cursor.execute("ALTER TABLE assets_new RENAME TO assets")
        
        # Recreate indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_assets_code ON assets (code)")
        
        conn.commit()
        logger.info(f"Migration completed: migrated {len(old_assets)} assets")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed: {e}", exc_info=True)
        raise
    finally:
        conn.close()


def _migrate_asset_instances_table(engine):
    """Migrate asset_instances table to add photo_file_id and price columns if needed."""
    import sqlite3
    from sqlalchemy import inspect
    
    db_path = Config.DB_PATH
    
    # Check if migration is needed
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    
    if 'asset_instances' not in table_names:
        # Table doesn't exist yet, no migration needed
        return
    
    columns = [col['name'] for col in inspector.get_columns('asset_instances')]
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Add photo_file_id column if needed
        if 'photo_file_id' not in columns:
            logger.info("Migrating asset_instances table: adding photo_file_id column")
            cursor.execute("ALTER TABLE asset_instances ADD COLUMN photo_file_id VARCHAR(255)")
            logger.info("Migration completed: added photo_file_id column to asset_instances")
        
        # Add price column if needed
        if 'price' not in columns:
            logger.info("Migrating asset_instances table: adding price column")
            cursor.execute("ALTER TABLE asset_instances ADD COLUMN price FLOAT")
            logger.info("Migration completed: added price column to asset_instances")
        
        conn.commit()
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed: {e}", exc_info=True)
        raise
    finally:
        conn.close()


def _migrate_operations_table(engine):
    """Migrate operations table to add price column if needed."""
    import sqlite3
    from sqlalchemy import inspect
    
    db_path = Config.DB_PATH
    
    # Check if migration is needed
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    
    if 'operations' not in table_names:
        # Table doesn't exist yet, no migration needed
        return
    
    columns = [col['name'] for col in inspector.get_columns('operations')]
    
    if 'price' in columns:
        # Migration not needed or already done
        return
    
    # Migration needed
    logger.info("Migrating operations table: adding price column")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Add price column
        cursor.execute("ALTER TABLE operations ADD COLUMN price FLOAT")
        
        conn.commit()
        logger.info("Migration completed: added price column to operations")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed: {e}", exc_info=True)
        raise
    finally:
        conn.close()


# ============================================================================
# Database Session Management
# ============================================================================

_engine = None
_SessionLocal = None


def get_session() -> Session:
    """Get database session."""
    global _engine, _SessionLocal
    if _engine is None:
        _engine = get_db_engine()
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    return _SessionLocal()


# ============================================================================
# DAO/Repository Functions for User
# ============================================================================

def create_user(
    telegram_id: int,
    fullname: str,
    role: str = UserRole.UNKNOWN.value,
    status: str = UserStatus.ACTIVE.value
) -> User:
    """Create a new user."""
    session = get_session()
    try:
        user = User(
            telegram_id=telegram_id,
            fullname=fullname,
            role=role,
            status=status
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user
    except Exception as e:
        session.rollback()
        raise
    finally:
        session.close()


def get_user_by_telegram_id(telegram_id: int) -> Optional[User]:
    """Get user by Telegram ID."""
    session = get_session()
    try:
        return session.query(User).filter(User.telegram_id == telegram_id).first()
    finally:
        session.close()


def get_user_by_id(user_id: int) -> Optional[User]:
    """Get user by ID."""
    session = get_session()
    try:
        return session.query(User).filter(User.id == user_id).first()
    finally:
        session.close()


def count_users() -> int:
    """Count total number of users in database."""
    session = get_session()
    try:
        return session.query(User).count()
    finally:
        session.close()


def get_all_users() -> list[User]:
    """Get all users from database."""
    session = get_session()
    try:
        return session.query(User).order_by(User.id).all()
    finally:
        session.close()


def update_user(
    user_id: int,
    fullname: Optional[str] = None,
    role: Optional[str] = None,
    status: Optional[str] = None
) -> Optional[User]:
    """Update user information."""
    session = get_session()
    try:
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            return None
        
        if fullname is not None:
            user.fullname = fullname
        if role is not None:
            user.role = role
        if status is not None:
            user.status = status
        
        session.commit()
        session.refresh(user)
        return user
    except Exception as e:
        session.rollback()
        raise
    finally:
        session.close()


# ============================================================================
# DAO/Repository Functions for Asset
# ============================================================================

def create_asset(
    name: str,
    qty: float = 0.0,
    category_id: Optional[int] = None,
    code: Optional[str] = None,
    owner_user_id: Optional[int] = None,
    price: Optional[float] = None,
    state: str = AssetState.IN_STOCK.value
) -> Asset:
    """Create a new asset."""
    session = get_session()
    try:
        asset = Asset(
            name=name,
            qty=qty,
            category_id=category_id,
            code=code,
            owner_user_id=owner_user_id,
            price=price,
            state=state
        )
        session.add(asset)
        session.commit()
        session.refresh(asset)
        return asset
    except Exception as e:
        session.rollback()
        raise
    finally:
        session.close()


def get_asset_by_id(asset_id: int) -> Optional[Asset]:
    """Get asset by ID."""
    session = get_session()
    try:
        return session.query(Asset).filter(Asset.id == asset_id).first()
    finally:
        session.close()


def get_asset_by_code(code: str) -> Optional[Asset]:
    """Get asset by code (QR/barcode)."""
    session = get_session()
    try:
        return session.query(Asset).filter(Asset.code == code).first()
    finally:
        session.close()


def get_all_assets() -> list[Asset]:
    """Get all assets from database."""
    session = get_session()
    try:
        return session.query(Asset).order_by(Asset.id).all()
    finally:
        session.close()


def update_asset(
    asset_id: int,
    name: Optional[str] = None,
    qty: Optional[float] = None,
    category_id: Optional[int] = None,
    code: Optional[str] = None,
    owner_user_id: Optional[int] = None,
    price: Optional[float] = None,
    state: Optional[str] = None
) -> Optional[Asset]:
    """Update asset information."""
    session = get_session()
    try:
        asset = session.query(Asset).filter(Asset.id == asset_id).first()
        if not asset:
            return None
        
        if name is not None:
            asset.name = name
        if qty is not None:
            asset.qty = qty
        if category_id is not None:
            asset.category_id = category_id
        if code is not None:
            asset.code = code
        if owner_user_id is not None:
            asset.owner_user_id = owner_user_id
        if price is not None:
            asset.price = price
        if state is not None:
            asset.state = state
        
        session.commit()
        session.refresh(asset)
        return asset
    except Exception as e:
        session.rollback()
        raise
    finally:
        session.close()


# ============================================================================
# DAO/Repository Functions for Operation
# ============================================================================

def create_operation(
    type: str,
    asset_id: int,
    qty: float,
    from_user_id: Optional[int] = None,
    to_user_id: Optional[int] = None,
    price: Optional[float] = None,
    comment: Optional[str] = None,
    photo_file_id: Optional[str] = None
) -> Operation:
    """Create a new operation."""
    session = get_session()
    try:
        operation = Operation(
            type=type,
            asset_id=asset_id,
            qty=qty,
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            price=price,
            comment=comment,
            photo_file_id=photo_file_id
        )
        session.add(operation)
        session.commit()
        session.refresh(operation)
        return operation
    except Exception as e:
        session.rollback()
        raise
    finally:
        session.close()


def get_operation_by_id(operation_id: int) -> Optional[Operation]:
    """Get operation by ID."""
    session = get_session()
    try:
        return session.query(Operation).filter(Operation.id == operation_id).first()
    finally:
        session.close()


def get_operations_by_asset_id(asset_id: int) -> list[Operation]:
    """Get all operations for a specific asset."""
    session = get_session()
    try:
        return session.query(Operation).filter(Operation.asset_id == asset_id).all()
    finally:
        session.close()


def update_operation(
    operation_id: int,
    type: Optional[str] = None,
    qty: Optional[float] = None,
    comment: Optional[str] = None,
    photo_file_id: Optional[str] = None
) -> Optional[Operation]:
    """Update operation information."""
    session = get_session()
    try:
        operation = session.query(Operation).filter(Operation.id == operation_id).first()
        if not operation:
            return None
        
        if type is not None:
            operation.type = type
        if qty is not None:
            operation.qty = qty
        if comment is not None:
            operation.comment = comment
        if photo_file_id is not None:
            operation.photo_file_id = photo_file_id
        
        session.commit()
        session.refresh(operation)
        return operation
    except Exception as e:
        session.rollback()
        raise
    finally:
        session.close()


# ============================================================================
# DAO/Repository Functions for Category
# ============================================================================

def get_all_categories() -> list[Category]:
    """Get all categories."""
    session = get_session()
    try:
        return session.query(Category).order_by(Category.name).all()
    finally:
        session.close()


def get_category_by_id(category_id: int) -> Optional[Category]:
    """Get category by ID."""
    session = get_session()
    try:
        return session.query(Category).filter(Category.id == category_id).first()
    finally:
        session.close()


def get_category_by_name(name: str) -> Optional[Category]:
    """Get category by name."""
    session = get_session()
    try:
        return session.query(Category).filter(Category.name == name).first()
    finally:
        session.close()


def create_category(name: str) -> Category:
    """Create a new category."""
    session = get_session()
    try:
        category = Category(name=name)
        session.add(category)
        session.commit()
        session.refresh(category)
        return category
    except Exception as e:
        session.rollback()
        raise
    finally:
        session.close()


# ============================================================================
# DAO/Repository Functions for AssetInstance
# ============================================================================

def create_asset_instance(
    asset_id: int,
    distinctive_features: str,
    state: str = AssetState.IN_STOCK.value,
    assigned_to_user_id: Optional[int] = None,
    photo_file_id: Optional[str] = None,
    price: Optional[float] = None
) -> AssetInstance:
    """Create a new asset instance."""
    session = get_session()
    try:
        instance = AssetInstance(
            asset_id=asset_id,
            distinctive_features=distinctive_features,
            state=state,
            assigned_to_user_id=assigned_to_user_id,
            photo_file_id=photo_file_id,
            price=price
        )
        session.add(instance)
        session.commit()
        session.refresh(instance)
        return instance
    except Exception as e:
        session.rollback()
        raise
    finally:
        session.close()


def get_asset_instances_by_asset_id(asset_id: int) -> list[AssetInstance]:
    """Get all instances for a specific asset."""
    session = get_session()
    try:
        return session.query(AssetInstance).filter(AssetInstance.asset_id == asset_id).all()
    finally:
        session.close()


def get_asset_instance_by_id(instance_id: int) -> Optional[AssetInstance]:
    """Get asset instance by ID."""
    session = get_session()
    try:
        return session.query(AssetInstance).filter(AssetInstance.id == instance_id).first()
    finally:
        session.close()


def get_next_instance_number(asset_id: int) -> int:
    """Get next instance number for auto-numbering."""
    session = get_session()
    try:
        instances = session.query(AssetInstance).filter(AssetInstance.asset_id == asset_id).all()
        # Find the highest number in existing instances
        max_num = 0
        for instance in instances:
            features = instance.distinctive_features
            if features.startswith("Экз. #"):
                try:
                    num = int(features.replace("Экз. #", ""))
                    max_num = max(max_num, num)
                except ValueError:
                    pass
        return max_num + 1
    finally:
        session.close()


def update_asset_instance(
    instance_id: int,
    distinctive_features: Optional[str] = None,
    state: Optional[str] = None,
    assigned_to_user_id: Optional[int] = None,
    photo_file_id: Optional[str] = None
) -> Optional[AssetInstance]:
    """Update asset instance information."""
    session = get_session()
    try:
        instance = session.query(AssetInstance).filter(AssetInstance.id == instance_id).first()
        if not instance:
            return None
        
        if distinctive_features is not None:
            instance.distinctive_features = distinctive_features
        if state is not None:
            instance.state = state
        if assigned_to_user_id is not None:
            instance.assigned_to_user_id = assigned_to_user_id
        if photo_file_id is not None:
            instance.photo_file_id = photo_file_id
        
        session.commit()
        session.refresh(instance)
        return instance
    except Exception as e:
        session.rollback()
        raise
    finally:
        session.close()


# ============================================================================
# Test Function
# ============================================================================

def test_db():
    """Test database operations."""
    print("=" * 60)
    print("Testing Database Operations")
    print("=" * 60)
    
    # Initialize database
    init_db()
    print("\n[OK] Database initialized")
    
    # Test User operations
    print("\n--- Testing User operations ---")
    user = create_user(
        telegram_id=123456789,
        fullname="Test User",
        role=UserRole.WORKER.value
    )
    print(f"[OK] Created user: ID={user.id}, telegram_id={user.telegram_id}, name={user.fullname}, role={user.role}")
    
    retrieved_user = get_user_by_telegram_id(123456789)
    print(f"[OK] Retrieved user: ID={retrieved_user.id}, name={retrieved_user.fullname}")
    
    updated_user = update_user(user.id, fullname="Updated Test User", role=UserRole.MANAGER.value)
    print(f"[OK] Updated user: name={updated_user.fullname}, role={updated_user.role}")
    
    # Test Asset operations
    print("\n--- Testing Asset operations ---")
    asset = create_asset(
        name="Test Asset",
        qty=10.0,
        category="tool",
        code="TEST-001",
        price=100.0
    )
    print(f"[OK] Created asset: ID={asset.id}, name={asset.name}, qty={asset.qty}, code={asset.code}")
    
    retrieved_asset = get_asset_by_id(asset.id)
    print(f"[OK] Retrieved asset: ID={retrieved_asset.id}, name={retrieved_asset.name}, qty={retrieved_asset.qty}")
    
    asset_by_code = get_asset_by_code("TEST-001")
    print(f"[OK] Retrieved asset by code: ID={asset_by_code.id}, name={asset_by_code.name}")
    
    updated_asset = update_asset(asset.id, qty=15.0, state=AssetState.IN_USE.value)
    print(f"[OK] Updated asset: qty={updated_asset.qty}, state={updated_asset.state}")
    
    # Test Operation operations
    print("\n--- Testing Operation operations ---")
    operation = create_operation(
        type=OperationType.INCOMING.value,
        asset_id=asset.id,
        qty=5.0,
        from_user_id=None,
        to_user_id=user.id,
        comment="Test incoming operation"
    )
    print(f"[OK] Created operation: ID={operation.id}, type={operation.type}, qty={operation.qty}, asset_id={operation.asset_id}")
    
    retrieved_operation = get_operation_by_id(operation.id)
    print(f"[OK] Retrieved operation: ID={retrieved_operation.id}, type={retrieved_operation.type}, comment={retrieved_operation.comment}")
    
    operations_list = get_operations_by_asset_id(asset.id)
    print(f"[OK] Retrieved {len(operations_list)} operations for asset ID={asset.id}")
    
    updated_operation = update_operation(operation.id, comment="Updated comment")
    print(f"[OK] Updated operation: comment={updated_operation.comment}")
    
    print("\n" + "=" * 60)
    print("All tests passed successfully!")
    print("=" * 60)
