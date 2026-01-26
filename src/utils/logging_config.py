"""Logging configuration module."""
import logging
import sys
from pathlib import Path
from src.config import Config


def setup_logging():
    """
    Configure logging for the application.
    
    Sets up:
    - File handler for logs/app.log
    - Console handler for development
    - Formatting with timestamp, level, and message
    - Log level from Config.LOG_LEVEL
    """
    # Ensure log directory exists
    log_dir = Path(Config.LOG_PATH).parent
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Get log level from config
    log_level = getattr(logging, Config.LOG_LEVEL.upper(), logging.DEBUG)
    
    # Create formatter
    formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()
    
    # File handler
    file_handler = logging.FileHandler(Config.LOG_PATH, encoding='utf-8')
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    # Console handler (for development)
    if Config.DEV_MODE:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
    
    return root_logger
