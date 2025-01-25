import asyncio
import logging
from telegram import Bot
from telegram.error import TelegramError
from .config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_THREAD_ID
from .notifications import TelegramNotifier

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def get_bot_info():
    """Get basic bot information"""
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        me = await bot.get_me()
        print(me)
        return {
            "id": me.id,
            "name": me.first_name,
            "username": me.username,
            "can_join_groups": me.can_join_groups,
            "can_read_all_group_messages": me.can_read_all_group_messages
        }
    except TelegramError as e:
        logger.error(f"Bot info error: {str(e)}")
        return None

async def get_active_chats():
    """Get list of chats where bot is present"""
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        updates = await bot.get_updates(limit=100, timeout=10)
        print(updates)
        
        chats = set()
        for update in updates:
            if update.message:
                chat = update.message.chat
                chats.add((chat.id, chat.type, chat.title or chat.username or chat.first_name))
        
        return sorted(chats, key=lambda x: x[0])
    except TelegramError as e:
        logger.error(f"Chat list error: {str(e)}")
        return None

async def test_connection():
    """Test bot connectivity and permissions"""
    logger.info("Starting Telegram bot tests...")
    
    # Test bot credentials
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not configured!")
        return False
        
    # Get bot info
    bot_info = await get_bot_info()
    if not bot_info:
        return False
        
    logger.info("\n🤖 *Bot Information*:")
    logger.info(f"ID: {bot_info['id']}")
    logger.info(f"Name: {bot_info['name']}")
    logger.info(f"Username: @{bot_info['username']}")
    logger.info(f"Can join groups: {bot_info['can_join_groups']}")
    logger.info(f"Can read messages: {bot_info['can_read_all_group_messages']}")
    
    # Get available chats
    chats = await get_active_chats()
    if chats:
        logger.info("\n📋 *Active Chats*:")
        for chat_id, chat_type, chat_name in chats:
            logger.info(f"{chat_id} ({chat_type}): {chat_name}")
    else:
        logger.warning("No active chats found - bot hasn't received any messages yet")
    
    # Test message sending
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        escaped_text = TelegramNotifier._escape_markdown_v2("✅ Bot connectivity test successful!")
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            message_thread_id=TELEGRAM_THREAD_ID,
            text=escaped_text,
            parse_mode='MarkdownV2'
        )
        logger.info("\nTest message sent successfully!")
        return True
    except TelegramError as e:
        logger.error(f"Message send failed: {str(e)}")
        return False

if __name__ == "__main__":
    asyncio.run(test_connection())