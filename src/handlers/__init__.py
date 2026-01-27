"""Handlers package."""
from src.handlers.start import router as start_router
from src.handlers.admin import router as admin_router
from src.handlers.operations import router as operations_router
from src.handlers.inventory import router as inventory_router
from src.handlers.user_reg import router as user_reg_router

__all__ = [
    "start_router",
    "admin_router",
    "operations_router",
    "inventory_router",
    "user_reg_router",
]
