"""Authentication and role middleware."""
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject


class AuthMiddleware(BaseMiddleware):
    """
    Middleware for user authentication and role assignment.
    
    Currently returns 'unknown' role for all users.
    In the future, this will check the database for user roles.
    """
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        """
        Process event and add user role to data.
        
        Args:
            handler: Next handler in the chain
            event: Telegram event (Message, CallbackQuery, etc.)
            data: Data dictionary passed to handlers
            
        Returns:
            Result of handler execution
        """
        # Get user ID from event
        user_id = None
        if hasattr(event, 'from_user') and event.from_user:
            user_id = event.from_user.id
        
        # For now, assign 'unknown' role to all users
        # TODO: Check database for actual user role
        user_role = "unknown"
        
        # Add role to data dictionary so handlers can access it
        data["user_role"] = user_role
        data["user_id"] = user_id
        
        # Call next handler
        return await handler(event, data)
