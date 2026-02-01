"""Main entry point for the Telegram bot."""
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from src.config import Config
from src.utils.logging_config import setup_logging
from src.middlewares.auth import AuthMiddleware
from src.services.db import init_db
from src.handlers import (
    start_router,
    admin_router,
    operations_router,
    inventory_router,
    user_reg_router,
)
from src.tasks.auto_signature import run_auto_signature_task


# Setup logging
setup_logging()
logger = logging.getLogger(__name__)


async def main():
    """Main function to start the bot."""
    # Ensure directories exist
    Config.create_dirs()
    
    # Initialize database (create tables if not exist)
    try:
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}", exc_info=True)
        raise
    
    # Check if BOT_TOKEN is set
    if not Config.BOT_TOKEN:
        logger.error("BOT_TOKEN is not set in .env file!")
        raise ValueError("BOT_TOKEN is required. Please set it in .env file.")
    
    # Initialize bot and dispatcher with FSM storage
    bot = Bot(token=Config.BOT_TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    
    # Register middleware
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())
    
    # Register routers
    dp.include_router(start_router)
    dp.include_router(admin_router)
    dp.include_router(operations_router)
    dp.include_router(inventory_router)
    dp.include_router(user_reg_router)
    
    logger.info("Starting bot...")
    
    # Delete webhook if exists (needed for polling mode)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Webhook deleted (if existed)")
    except Exception as e:
        logger.warning(f"Failed to delete webhook: {e}")
    
    # Start background task for auto-signature
    auto_signature_task = asyncio.create_task(run_auto_signature_task(bot))
    logger.info("Auto-signature background task started")
    
    try:
        # Start polling
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Error occurred: {e}", exc_info=True)
    finally:
        auto_signature_task.cancel()
        try:
            await auto_signature_task
        except asyncio.CancelledError:
            pass
        await bot.session.close()
        logger.info("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
