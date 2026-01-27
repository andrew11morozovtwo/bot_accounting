"""Database models and schema definitions."""
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


class Asset(Base):
    """
    Asset (Material values) table.
    
    Fields:
        id: Primary key
        name: Asset name
        category: Asset category
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
    category = Column(String(100), nullable=True)
    code = Column(String(100), unique=True, nullable=True, index=True)  # QR/barcode
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    qty = Column(Float, nullable=False, default=0.0)
    price = Column(Float, nullable=True)  # Price per unit
    state = Column(String(50), nullable=False, default=AssetState.IN_STOCK.value)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    owner = relationship("User", back_populates="owned_assets", foreign_keys=[owner_user_id])
    operations = relationship("Operation", back_populates="asset")


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
        timestamp: Operation timestamp
        comment: Comment or reason for operation
        photo_file_id: Telegram file_id (not stored, nullable for future use)
    """
    __tablename__ = "operations"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String(50), nullable=False)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False)
    from_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    to_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    qty = Column(Float, nullable=False)
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
    """Initialize database: create all tables."""
    engine = get_db_engine()
    Base.metadata.create_all(engine)
    return engine


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
    category: Optional[str] = None,
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
            category=category,
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


def update_asset(
    asset_id: int,
    name: Optional[str] = None,
    qty: Optional[float] = None,
    category: Optional[str] = None,
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
        if category is not None:
            asset.category = category
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
