import os
import logging
from typing import List, Dict
from .config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_THREAD_ID
import requests
from telegram import Bot
import asyncio

logger = logging.getLogger(__name__)

class TelegramNotifier:
    def __init__(self):
        self.bot = Bot(token=TELEGRAM_BOT_TOKEN)
        
    @staticmethod
    def _escape_markdown_v2(text: str) -> str:
        """Escape special characters for MarkdownV2"""
        special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        escaped_text = ''
        for char in str(text):
            if char in special_chars:
                escaped_text += f'\\{char}'
            else:
                escaped_text += char
        return escaped_text

    async def _send_message(self, message: str) -> bool:
        """Async message sender with thread support"""
        try:
            if not TELEGRAM_CHAT_ID:
                logger.error("Telegram chat ID not configured!")
                return False
            
            logger.info(f"Sending to chat: {TELEGRAM_CHAT_ID}, thread: {TELEGRAM_THREAD_ID}")
            
            await self.bot.send_message(
                chat_id=str(TELEGRAM_CHAT_ID),
                message_thread_id=int(TELEGRAM_THREAD_ID) if TELEGRAM_THREAD_ID else None,
                text=message,
                parse_mode='MarkdownV2',
                disable_web_page_preview=True
            )
            return True
        except Exception as e:
            logger.error(f"Telegram error: {type(e)} - {str(e)}")
            logger.info("Please verify:")
            logger.info(f"1. Bot is added to chat {TELEGRAM_CHAT_ID}")
            logger.info(f"2. Thread {TELEGRAM_THREAD_ID} exists")
            logger.info(f"3. Bot has 'Send Messages' permission")
            return False

    def send_alert(self, recommendations: List[Dict]) -> bool:
        """Main alert method"""
        if not recommendations:
            logger.info("No recommendations to send")
            return False
            
        message = self._format_recommendation(recommendations)
        return asyncio.run(self._send_message(message))

    def _format_recommendation(self, recommendations: List[Dict]) -> str:
        """Format recommendations considering positions"""
        header = "📊 *Yield Optimization Recommendations* 📊\n\n"
        rows = []
        
        for rec in recommendations[:5]:  # Limit to top 5
            # Escape all values
            asset = self._escape_markdown_v2(rec['asset'])
            from_chain = self._escape_markdown_v2(rec['from_chain'])
            to_chain = self._escape_markdown_v2(rec['to_chain'])
            current_apy = self._escape_markdown_v2(str(rec['current_apy']))
            target_apy = self._escape_markdown_v2(str(rec['target_apy']))
            profit = self._escape_markdown_v2(str(rec['estimated_profit']))
            gas = self._escape_markdown_v2(str(rec['gas_cost']))
            position = self._escape_markdown_v2(f"{rec['position_size']:,.2f}")
            
            row = (
                f"• *{asset}*: {from_chain} ➡️ {to_chain}\n"
                f"  Current APY: `{current_apy}%` → New APY: `{target_apy}%`\n"
                f"  Profit: `{profit}%` \\(Gas: ${gas}\\)\n"
                f"  Position: `${position}`\n"
            )
            rows.append(row)
        
        footer = f"\n🔔 Found *{len(recommendations)}* opportunities"
        return header + '\n'.join(rows) + footer

def send_telegram_alert(recommendations: List[Dict]) -> bool:
    """Legacy function wrapper"""
    return TelegramNotifier().send_alert(recommendations)