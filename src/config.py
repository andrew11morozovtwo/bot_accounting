"""Configuration module for the bot."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Application configuration loaded from environment variables."""
    
    # Telegram Bot
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    
    # Google Sheets
    GOOGLE_SHEETS_ID: str = os.getenv("GOOGLE_SHEETS_ID", "")
    GOOGLE_CREDENTIALS_PATH: str = os.getenv("GOOGLE_CREDENTIALS_PATH", "./credentials/service_account.json")
    
    # Admin
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "0000")
    
    # Paths
    BASE_DIR: str = os.getenv("BASE_DIR", "./")
    DB_PATH: str = os.getenv("DB_PATH", "./data/db.sqlite3")
    LOG_PATH: str = os.getenv("LOG_PATH", "./logs/app.log")
    
    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "DEBUG")
    
    # Google Sheets Settings
    DEFAULT_SHEET_NAME: str = os.getenv("DEFAULT_SHEET_NAME", "Лист1")
    MAX_FILE_SIZE: int = int(os.getenv("MAX_FILE_SIZE", "10485760"))
    
    # Environment Flags
    DEV_MODE: bool = os.getenv("DEV_MODE", "true").lower() == "true"
    USE_WEBHOOK: bool = os.getenv("USE_WEBHOOK", "false").lower() == "true"
    MOCK_SHEETS: bool = os.getenv("MOCK_SHEETS", "false").lower() == "true"
    
    @classmethod
    def _normalize_path(cls, path: str, base_dir: str = None) -> str:
        """Normalize a path relative to BASE_DIR."""
        if base_dir is None:
            base_dir = cls.BASE_DIR
        
        # Convert to absolute path
        if not os.path.isabs(path):
            path = os.path.join(base_dir, path)
        
        # Normalize the path
        return os.path.normpath(path)
    
    @classmethod
    def _init_paths(cls):
        """Initialize and normalize all paths."""
        cls.BASE_DIR = os.path.normpath(os.path.abspath(cls.BASE_DIR))
        cls.DB_PATH = cls._normalize_path(cls.DB_PATH)
        cls.LOG_PATH = cls._normalize_path(cls.LOG_PATH)
        cls.GOOGLE_CREDENTIALS_PATH = cls._normalize_path(cls.GOOGLE_CREDENTIALS_PATH)
    
    @classmethod
    def create_dirs(cls):
        """Create necessary directories if they don't exist."""
        cls._init_paths()
        
        # Create directories
        dirs_to_create = [
            os.path.dirname(cls.DB_PATH),  # data/
            os.path.dirname(cls.LOG_PATH),  # logs/
            os.path.dirname(cls.GOOGLE_CREDENTIALS_PATH),  # credentials/
        ]
        
        for dir_path in dirs_to_create:
            if dir_path:  # Skip if empty (e.g., if path is in current dir)
                Path(dir_path).mkdir(parents=True, exist_ok=True)


# Initialize paths on module import
Config._init_paths()
