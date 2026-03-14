"""
TradeRadar - Telegram Bot
Handles user commands and sends automated alerts.
"""
import logging
import asyncio
from datetime import datetime
from telegram import Update, Bot
from telegram.constants import ParseMode
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_ENABLED

logger = logging.getLogger(__name__)


class TelegramService:
    """Telegram bot for sending alerts and handling commands."""

    def __init__(self):
        self.enabled = TELEGRAM_ENABLED
        self.bot_token = TELEGRAM_BOT_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.bot = Bot(token=self.bot_token) if self.enabled else None

    async def send_message(self, text: str, parse_mode: str = ParseMode.MARKDOWN) -> bool:
        """Send a message to the configured chat."""
        if not self.enabled or not self.bot:
            logger.warning("Telegram is disabled")
            return False

        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode=parse_mode,
            )
            logger.info(f"Telegram message sent successfully")
            return True
        except Exception as e:
            logger.error(f"Telegram send error: {e}")
            # Try without parse_mode if markdown fails
            try:
                await self.bot.send_message(
                    chat_id=self.chat_id,
                    text=text,
                )
                return True
            except Exception as e2:
                logger.error(f"Telegram send error (plain): {e2}")
                return False

    def send_message_sync(self, text: str, parse_mode: str = ParseMode.MARKDOWN) -> bool:
        """Synchronous wrapper for send_message."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're inside an async context, create a task
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, self.send_message(text, parse_mode))
                    return future.result(timeout=15)
            else:
                return loop.run_until_complete(self.send_message(text, parse_mode))
        except RuntimeError:
            return asyncio.run(self.send_message(text, parse_mode))

    async def send_alert(self, alert_message: str) -> bool:
        """Send a trading alert."""
        return await self.send_message(alert_message)

    async def send_startup_message(self) -> bool:
        """Send a startup notification."""
        msg = (
            "🚀 *TradeRadar Iniciado*\n\n"
            f"⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n"
            "📡 Monitorizando activos...\n\n"
            "Comandos disponibles via API:\n"
            "• `GET /api/portfolio` → Ver cartera\n"
            "• `GET /api/signals` → Ver señales\n"
            "• `GET /api/market/prices` → Precios actuales\n"
        )
        return await self.send_message(msg)

    async def send_portfolio_summary(self, portfolio_data: dict) -> bool:
        """Send portfolio summary via Telegram."""
        msg = "💼 *RESUMEN DE CARTERA*\n\n"

        entries = portfolio_data.get("entries", [])
        if not entries:
            msg += "Cartera vacía. Añade activos via el dashboard.\n"
        else:
            total_invested = 0
            total_current = 0

            for entry in entries:
                pnl = entry.get("pnl", 0)
                pnl_emoji = "📈" if pnl >= 0 else "📉"
                msg += f"*{entry['symbol']}*\n"
                msg += f"  Cantidad: {entry['quantity']}\n"
                msg += f"  Compra: €{entry['avg_buy_price']:,.2f}\n"
                msg += f"  Actual: €{entry['current_price']:,.2f}\n"
                msg += f"  {pnl_emoji} P&L: €{pnl:,.2f} ({entry['pnl_pct']:+.1f}%)\n\n"
                total_invested += entry.get("total_invested", 0)
                total_current += entry.get("current_value", 0)

            total_pnl = total_current - total_invested
            total_emoji = "📈" if total_pnl >= 0 else "📉"
            msg += f"{'─' * 25}\n"
            msg += f"💰 Total invertido: €{total_invested:,.2f}\n"
            msg += f"💎 Valor actual: €{total_current:,.2f}\n"
            msg += f"{total_emoji} *P&L Total: €{total_pnl:,.2f}*\n"

        return await self.send_message(msg)

    async def test_connection(self) -> bool:
        """Test if bot can connect and send."""
        try:
            me = await self.bot.get_me()
            logger.info(f"Telegram bot connected: @{me.username}")
            return True
        except Exception as e:
            logger.error(f"Telegram connection test failed: {e}")
            return False
