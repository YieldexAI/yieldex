import os
from common.config import validate_base_env_vars, logger

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_THREAD_ID = os.getenv("TELEGRAM_THREAD_ID", "")

def validate_env_vars() -> bool:
    """Validate environment variables for telegram bot"""
    if not validate_base_env_vars():
        return False
        
    if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
        logger.error("Telegram credentials not properly configured!")
        return False
        
    return True 