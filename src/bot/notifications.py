import os
import logging
import time
from typing import List, Dict
from ..common.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_THREAD_ID
import requests
from telegram import Bot
import asyncio
from .analytics import get_top_asset_overall, get_top_asset_by_chain, get_top_growing_asset, get_top3_base_apy, get_latest_apy_data, get_top_apy_pools
from telegram.error import RetryAfter

logger = logging.getLogger(__name__)

class TelegramNotifier:
    def __init__(self, alert_config: dict = None):
        self.config = alert_config or {
            'send_overall': True,
            'send_chains': ['Ethereum', 'Polygon', 'Arbitrum'],
            'send_growth': False,
            'send_top3_base': True
        }
        self.bot = None  # Инициализируем позже
        self._growth_data = None
        
    def run_alerting(self):
        """Main alerting workflow"""
        latest_apy = get_latest_apy_data()
        top_pools = get_top_apy_pools(latest_apy, limit=5)
        
        self.send_top_asset_alerts(latest_apy)
        
        if top_pools:
            self.send_top_apy_alert(top_pools)
        
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
        """Async message sender with flood control"""
        try:
            if not TELEGRAM_CHAT_ID:
                logger.error("Telegram chat ID not configured!")
                return False
            
            # Создаем новый экземпляр Bot при каждом вызове
            self.bot = Bot(token=TELEGRAM_BOT_TOKEN)
            
            logger.info(f"Sending to chat: {TELEGRAM_CHAT_ID}, thread: {TELEGRAM_THREAD_ID}")
            
            await self.bot.send_message(
                chat_id=str(TELEGRAM_CHAT_ID),
                message_thread_id=int(TELEGRAM_THREAD_ID) if TELEGRAM_THREAD_ID else None,
                text=message,
                parse_mode='MarkdownV2',
                disable_web_page_preview=True
            )
            return True
        
        except RetryAfter as e:
            wait_time = e.retry_after
            logger.warning(f"Flood control: Waiting {wait_time}s")
            await asyncio.sleep(wait_time)
            return await self._send_message(message)  # Retry
        
        except Exception as e:
            logger.error(f"Telegram error: {type(e)} - {str(e)}")
            logger.info("Please verify:")
            logger.info(f"1. Bot is added to chat {TELEGRAM_CHAT_ID}")
            logger.info(f"2. Thread {TELEGRAM_THREAD_ID} exists")
            logger.info(f"3. Bot has 'Send Messages' permission")
            return False
        finally:
            if self.bot:
                await self.bot.close()
                await asyncio.sleep(1)  # Добавляем небольшую паузу после закрытия

    def send_alert(self, recommendations: List[Dict]) -> bool:
        """Main alert method"""
        if not recommendations:
            logger.info("No recommendations to send")
            return False
            
        message = self._format_recommendation(recommendations)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(self._send_message(message))

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

    def _format_top_apy(self, top_pools: List[Dict]) -> str:
        """Format top APY pools message with improved formatting"""
        header = "✨ *TOP STABLE OPPORTUNITIES* ✨\n\n"
        rows = []
        
        for i, pool in enumerate(top_pools[:5], 1):
            asset = self._escape_markdown_v2(pool['asset'])
            chain = self._escape_markdown_v2(pool['chain'])
            protocol_part = pool['pool_id'].split('_')[2]
            protocol_name = protocol_part.split('-')[0].capitalize()
            protocol = self._escape_markdown_v2(protocol_name)
            apy = self._escape_markdown_v2(f"{pool['apy']:.2f}")
            
            # Fix TVL formatting
            tvl_usd = pool['tvl']
            if tvl_usd >= 1_000_000:
                tvl_str = f"${tvl_usd/1_000_000:.1f}M"
            elif tvl_usd >= 1_000:
                tvl_str = f"${tvl_usd/1_000:.1f}K"
            else:
                tvl_str = f"${tvl_usd:,.0f}"
            tvl = self._escape_markdown_v2(tvl_str)
            
            number = self._escape_markdown_v2(f"#{i}")
            
            rows.append(
                f"🏆 *{number}*\n"
                f"┌ *Asset*: {asset}\n"
                f"├ *Chain*: {chain}\n"
                f"├ *Protocol*: {protocol}\n"
                f"├ *APY*: `{apy}%`\n"
                f"└ *TVL*: `{tvl}`\n"
            )
        
        total = self._escape_markdown_v2(str(len(top_pools)))
        footer = f"\n🔍 Found *{total}* high\\-yield pools"
        return header + '\n'.join(rows) + footer

    def send_top_apy_alert(self, top_pools: List[Dict]) -> bool:
        """Send top APY pools alert"""
        if not top_pools:
            logger.info("No top APY pools to send")
            return False
            
        message = self._format_top_apy(top_pools)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(self._send_message(message))

    def _format_asset_alert(self, asset_data: Dict, title: str) -> str:
        """Generic format for asset alerts"""
        asset = self._escape_markdown_v2(asset_data['asset'])
        chain = self._escape_markdown_v2(asset_data.get('chain', 'Multi-chain'))
        apy = self._escape_markdown_v2(f"{asset_data['apy']:.2f}")
        apy_base = self._escape_markdown_v2(f"{asset_data.get('apyBase', 0):.2f}")
        tvl = self._escape_markdown_v2(f"${asset_data['tvl']/1_000_000:.1f}M")
        protocol = self._escape_markdown_v2(asset_data['pool_id'].split('_')[2].capitalize())

        return (
            f"🏆 *{title}* 🏆\n\n"
            f"• *Asset*: {asset}\n"
            f"• *Chain*: {chain}\n"
            f"• *Protocol*: {protocol}\n"
            f"• *Total APY*: `{apy}%`\n"
            f"• *Base APY*: `{apy_base}%`\n"
            f"• *TVL*: `{tvl}`\n"
        )

    def send_top_asset_alerts(self, latest_apy: List[Dict]):
        """Основной метод отправки всех алертов"""
        messages = []
        
        # Формирование всех алертов на основе полученных данных
        if self.config['send_overall']:
            top_overall = get_top_asset_overall(latest_apy)
            if top_overall:
                messages.append(self._format_asset_alert(top_overall, "Top Overall Asset"))
        
        # Обработка цепей
        chains_to_process = self.config['send_chains'] or list({p['chain'] for p in latest_apy})
        
        for chain in chains_to_process:
            top_chain = get_top_asset_by_chain(latest_apy, chain)
            if top_chain:
                messages.append(self._format_asset_alert(top_chain, f"Top {chain} Asset"))
        
        # Growing asset
        if self.config['send_growth']:
            top_growth = get_top_growing_asset()
            if top_growth:
                messages.append(self._format_growth_alert(top_growth))
        
        # Top 3 Base APY
        if self.config['send_top3_base']:
            top3_base = get_top3_base_apy(latest_apy)
            if top3_base:
                messages.append(self._format_top3_base_alert(top3_base))
        
        # Создаем и запускаем event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Отправляем сообщения с задержкой
            results = []
            for i, msg in enumerate(messages):
                # Добавляем задержку между сообщениями
                if i > 0:
                    time.sleep(3)  # 3 секунды между сообщениями
                
                results.append(loop.run_until_complete(self._send_message(msg)))
            
            return all(results)
        finally:
            loop.close()

    def _get_growth_data(self):
        """Получение данных роста APY с кэшированием"""
        if not self._growth_data:
            self._growth_data = get_top_growing_asset()
        return self._growth_data

    def _format_growth_alert(self, growth_data: Dict) -> str:
        """Форматирование алерта роста APY"""
        growth = self._escape_markdown_v2(f"+{growth_data['growth']:.2f}%")
        apy_formatted = self._escape_markdown_v2(f"{growth_data['apy']:.2f}")
        return (
            f"📈 *Highest APY Growth (24h)* 📈\n\n"
            f"• *Asset*: {self._escape_markdown_v2(growth_data['asset'])}\n"
            f"• *Chain*: {self._escape_markdown_v2(growth_data['chain'])}\n"
            f"• *Growth*: `{growth}`\n"
            f"• *Current APY*: `{apy_formatted}%`\n"
        )

    def _format_top3_base_alert(self, top3_base: List[Dict]) -> str:
        """Форматирование топ-3 базовых APY"""
        message = "🥇🥈🥉 *Top 3 Base APY Leaders* 🥇🥈🥉\n\n"
        for i, asset in enumerate(top3_base, 1):
            apy_base_formatted = self._escape_markdown_v2(f"{asset['apyBase']:.2f}")
            tvl_formatted = self._escape_markdown_v2(f"{asset['tvl']/1_000_000:.1f}")
            entry = (
                f"{i}. *{self._escape_markdown_v2(asset['asset'])}* "
                f"({self._escape_markdown_v2(asset['chain'])})\n"
                f"   `{apy_base_formatted}%` "
                f"TVL: `${tvl_formatted}M`\n"
            )
            message += entry
        return message

def send_telegram_alert(recommendations: List[Dict]) -> bool:
    """Legacy function wrapper"""
    return TelegramNotifier().send_alert(recommendations)

def send_top_apy_alert(top_pools: List[Dict]) -> bool:
    """Legacy function wrapper for top APY alert"""
    return TelegramNotifier().send_top_apy_alert(top_pools)

if __name__ == "__main__":
    TelegramNotifier().run_alerting()