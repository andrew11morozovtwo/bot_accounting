"""Background task for auto-signing operations after 24 hours."""
import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot

from src.config import Config
from src.services.db import (
    get_unsigned_outgoing_operations,
    update_operation_signature,
    get_user_by_id,
    get_operation_by_id,
    get_asset_by_id
)

logger = logging.getLogger(__name__)


async def auto_sign_operations(bot: Bot):
    """Auto-sign operations that are older than 24 hours and haven't been signed."""
    try:
        operations = get_unsigned_outgoing_operations()
        
        for operation in operations:
            try:
                # Check if operation is really older than 24 hours
                if operation.timestamp and (datetime.now() - operation.timestamp) >= timedelta(hours=24):
                    # Update operation with auto-signature
                    update_operation_signature(
                        operation_id=operation.id,
                        signed_by_user_id=operation.to_user_id,
                        auto_signed=True
                    )
                    
                    # Get recipient user
                    recipient_user = get_user_by_id(operation.to_user_id)
                    if recipient_user:
                        # Get asset info
                        asset = get_asset_by_id(operation.asset_id)
                        asset_name = asset.name if asset else "Неизвестный актив"
                        
                        # Send notification to recipient
                        notification_text = (
                            "⏰ <b>Автоматическое подписание акта передачи имущества</b>\n\n"
                            f"Операция передачи имущества <b>{asset_name}</b> "
                            f"была автоматически подписана через 24 часа после передачи.\n\n"
                            "Вы несете ответственность за сохранность переданного имущества."
                        )
                        
                        try:
                            await bot.send_message(
                                chat_id=recipient_user.telegram_id,
                                text=notification_text,
                                parse_mode="HTML"
                            )
                            logger.info(
                                f"Auto-signed operation {operation.id} and notified user {recipient_user.id}"
                            )
                        except Exception as e:
                            logger.error(
                                f"Failed to send auto-signature notification to user {recipient_user.id}: {e}"
                            )
                    else:
                        logger.warning(f"Recipient user {operation.to_user_id} not found for operation {operation.id}")
                    
            except Exception as e:
                logger.error(f"Error processing auto-signature for operation {operation.id}: {e}", exc_info=True)
                
    except Exception as e:
        logger.error(f"Error in auto_sign_operations: {e}", exc_info=True)


async def run_auto_signature_task(bot: Bot):
    """Run auto-signature task periodically."""
    while True:
        try:
            await auto_sign_operations(bot)
            # Run every hour to check for operations that need auto-signing
            await asyncio.sleep(3600)  # 1 hour
        except Exception as e:
            logger.error(f"Error in run_auto_signature_task: {e}", exc_info=True)
            await asyncio.sleep(3600)  # Wait before retrying
