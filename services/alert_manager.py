"""
TradeRadar - Alert Manager
Manages alert delivery, cooldowns, and rate limiting.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from database.models import Alert
from config import ALERT_COOLDOWN_MINUTES, MAX_ALERTS_PER_HOUR

logger = logging.getLogger(__name__)


class AlertManager:
    """Manages when and how alerts are sent to avoid spam."""

    def should_send_alert(self, db: Session, asset_id: int, signal_type: str) -> bool:
        """Check if we should send this alert (cooldown + rate limiting)."""
        now = datetime.utcnow()

        # ─── Check cooldown for same asset + signal ─────
        cooldown_cutoff = now - timedelta(minutes=ALERT_COOLDOWN_MINUTES)
        recent_same = (
            db.query(Alert)
            .filter(
                Alert.asset_id == asset_id,
                Alert.signal_type == signal_type,
                Alert.sent_telegram == True,
                Alert.created_at >= cooldown_cutoff,
            )
            .first()
        )
        if recent_same:
            logger.debug(f"Alert cooldown active for asset {asset_id} signal {signal_type}")
            return False

        # ─── Check rate limit ──────────────────────────
        hour_ago = now - timedelta(hours=1)
        alerts_last_hour = (
            db.query(Alert)
            .filter(Alert.sent_telegram == True, Alert.created_at >= hour_ago)
            .count()
        )
        if alerts_last_hour >= MAX_ALERTS_PER_HOUR:
            logger.warning(f"Rate limit reached: {alerts_last_hour} alerts in last hour")
            return False

        return True

    def format_alert_message(self, signal_data: dict) -> str:
        """Format a signal into a rich Telegram message."""
        analysis = signal_data.get("analysis", {})
        rec = signal_data.get("recommendation", {})
        portfolio = signal_data.get("portfolio_details")

        signal = analysis.get("signal", "HOLD")
        signal_emoji = {
            "STRONG_BUY": "🟢🟢 COMPRA FUERTE",
            "BUY": "🟢 COMPRA",
            "HOLD": "🟡 MANTENER",
            "SELL": "🔴 VENTA",
            "STRONG_SELL": "🔴🔴 VENTA FUERTE",
        }

        urgency_emoji = {"HIGH": "🚨", "MEDIUM": "⚠️", "LOW": "ℹ️"}

        msg = f"{'═' * 30}\n"
        msg += f"📊 *TRADERADAR ALERT*\n"
        msg += f"{'═' * 30}\n\n"
        msg += f"*{signal_data['symbol']}* ({signal_data['name']})\n"
        msg += f"Tipo: {signal_data['asset_type'].upper()}\n"
        msg += f"💰 Precio: €{signal_data['current_price']:,.2f}\n\n"

        msg += f"*Señal: {signal_emoji.get(signal, signal)}*\n"
        msg += f"📈 Confianza: {analysis.get('confidence', 0):.0f}%\n\n"

        # Portfolio info
        if portfolio:
            pnl = portfolio['pnl']
            pnl_emoji = "📈" if pnl >= 0 else "📉"
            msg += f"*💼 Tu Posición:*\n"
            msg += f"  Cantidad: {portfolio['quantity']}\n"
            msg += f"  Precio compra: €{portfolio['avg_buy_price']:,.2f}\n"
            msg += f"  Invertido: €{portfolio['total_invested']:,.2f}\n"
            msg += f"  Valor actual: €{portfolio['current_value']:,.2f}\n"
            msg += f"  {pnl_emoji} P&L: €{pnl:,.2f} ({portfolio['pnl_pct']:+.1f}%)\n\n"

        # Recommendation
        if rec:
            urgency = urgency_emoji.get(rec.get("urgency", "LOW"), "ℹ️")
            msg += f"*{urgency} Recomendación: {rec.get('action', 'N/A')}*\n"
            msg += f"_{rec.get('reason', '')}_\n\n"

        # Indicators summary
        indicators = analysis.get("indicators", [])
        if indicators:
            msg += f"*📉 Indicadores:*\n"
            for ind in indicators:
                ind_emoji = "🟢" if ind["signal"] == "BUY" else ("🔴" if ind["signal"] == "SELL" else "🟡")
                msg += f"  {ind_emoji} {ind['name']}: {ind['description']}\n"

        msg += f"\n⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
        return msg
