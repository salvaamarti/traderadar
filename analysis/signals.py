"""
TradeRadar - Signal Generator
Evaluates assets against portfolio to generate buy/sell recommendations.
"""
import json
import logging
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from database.models import Asset, PortfolioEntry, PriceHistory, Alert
from analysis.technical import TechnicalAnalyzer, AnalysisResult

logger = logging.getLogger(__name__)


class SignalGenerator:
    """Generates trading signals by combining technical analysis with portfolio context."""

    def __init__(self):
        self.analyzer = TechnicalAnalyzer()

    def evaluate_asset(
        self,
        db: Session,
        asset: Asset,
        df,
        current_price: float,
    ) -> Optional[dict]:
        """
        Evaluate an asset and generate a signal with portfolio context.

        For assets in portfolio: calculates P&L and recommends sell if profitable + bearish signal.
        For watchlist assets: recommends buy if strong bullish signal.
        """
        # Run technical analysis
        analysis = self.analyzer.analyze(df, symbol=asset.symbol)
        if not analysis:
            return None

        # Check portfolio
        portfolio_entries = (
            db.query(PortfolioEntry)
            .filter(PortfolioEntry.asset_id == asset.id, PortfolioEntry.sold == False)
            .all()
        )

        result = {
            "asset_id": asset.id,
            "symbol": asset.symbol,
            "name": asset.name,
            "asset_type": asset.asset_type,
            "current_price": current_price,
            "analysis": analysis.to_dict(),
            "in_portfolio": len(portfolio_entries) > 0,
            "portfolio_details": None,
            "recommendation": None,
        }

        if portfolio_entries:
            # Asset is in our portfolio — check for sell opportunities
            total_qty = sum(e.quantity for e in portfolio_entries)
            total_invested = sum(e.total_invested for e in portfolio_entries)
            avg_buy_price = total_invested / total_qty if total_qty > 0 else 0
            current_value = total_qty * current_price
            pnl = current_value - total_invested
            pnl_pct = ((current_price - avg_buy_price) / avg_buy_price * 100) if avg_buy_price > 0 else 0

            result["portfolio_details"] = {
                "quantity": total_qty,
                "avg_buy_price": round(avg_buy_price, 2),
                "total_invested": round(total_invested, 2),
                "current_value": round(current_value, 2),
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 2),
            }

            # Generate recommendation
            if pnl > 0 and analysis.signal in ("SELL", "STRONG_SELL"):
                result["recommendation"] = {
                    "action": "SELL",
                    "reason": f"Beneficio de €{pnl:.2f} ({pnl_pct:.1f}%) + señal técnica bajista",
                    "urgency": "HIGH" if analysis.signal == "STRONG_SELL" else "MEDIUM",
                }
            elif pnl > 0 and analysis.signal == "HOLD":
                result["recommendation"] = {
                    "action": "HOLD",
                    "reason": f"En beneficio €{pnl:.2f} ({pnl_pct:.1f}%), indicadores neutrales",
                    "urgency": "LOW",
                }
            elif pnl < 0 and analysis.signal in ("BUY", "STRONG_BUY"):
                result["recommendation"] = {
                    "action": "HOLD_OR_BUY_MORE",
                    "reason": f"En pérdida €{pnl:.2f} ({pnl_pct:.1f}%) pero señal alcista. Posible recuperación.",
                    "urgency": "MEDIUM",
                }
            elif pnl < 0 and analysis.signal in ("SELL", "STRONG_SELL"):
                result["recommendation"] = {
                    "action": "CONSIDER_SELL",
                    "reason": f"En pérdida €{pnl:.2f} ({pnl_pct:.1f}%) + señal bajista. Considerar stop-loss.",
                    "urgency": "HIGH" if analysis.signal == "STRONG_SELL" else "MEDIUM",
                }
            else:
                result["recommendation"] = {
                    "action": "HOLD",
                    "reason": f"P&L: €{pnl:.2f} ({pnl_pct:.1f}%). Sin señal clara.",
                    "urgency": "LOW",
                }
        else:
            # Asset is on watchlist only — check for buy opportunities
            if analysis.signal in ("BUY", "STRONG_BUY") and analysis.confidence >= 50:
                result["recommendation"] = {
                    "action": "BUY",
                    "reason": f"Señal técnica alcista con {analysis.confidence:.0f}% confianza",
                    "urgency": "HIGH" if analysis.signal == "STRONG_BUY" else "MEDIUM",
                }
            elif analysis.signal in ("SELL", "STRONG_SELL"):
                result["recommendation"] = {
                    "action": "AVOID",
                    "reason": f"Señal técnica bajista. No es buen momento para comprar.",
                    "urgency": "LOW",
                }
            else:
                result["recommendation"] = {
                    "action": "WATCH",
                    "reason": f"Indicadores neutrales. Seguir monitorizando.",
                    "urgency": "LOW",
                }

        return result

    def save_alert(self, db: Session, signal_data: dict) -> Optional[Alert]:
        """Save a generated signal as an alert in the database."""
        try:
            analysis = signal_data.get("analysis", {})
            rec = signal_data.get("recommendation", {})

            alert = Alert(
                asset_id=signal_data["asset_id"],
                signal_type=analysis.get("signal", "HOLD"),
                confidence=analysis.get("confidence", 0),
                current_price=signal_data["current_price"],
                message=rec.get("reason", ""),
                details=json.dumps(analysis.get("indicators", [])),
                sent_telegram=False,
            )
            db.add(alert)
            db.commit()
            db.refresh(alert)
            return alert
        except Exception as e:
            logger.error(f"Error saving alert: {e}")
            db.rollback()
            return None
