"""
TradeRadar - Price Tracker Service
Scheduled service that fetches prices and runs analysis.
"""
import pandas as pd
import logging
import asyncio
from datetime import datetime
from sqlalchemy.orm import Session
from database.db import SessionLocal
from database.models import Asset, PriceHistory
from services.coingecko import CoinGeckoClient
from services.yahoo_finance import YahooFinanceClient
from analysis.technical import TechnicalAnalyzer
from analysis.signals import SignalGenerator
from services.alert_manager import AlertManager
from services.telegram_bot import TelegramService
from config import SIGNAL_CONFIDENCE_MIN

logger = logging.getLogger(__name__)


class PriceTracker:
    """Fetches prices, runs analysis, and triggers alerts."""

    def __init__(self):
        self.coingecko = CoinGeckoClient()
        self.yahoo = YahooFinanceClient()
        self.analyzer = TechnicalAnalyzer()
        self.signal_gen = SignalGenerator()
        self.alert_mgr = AlertManager()
        self.telegram = TelegramService()

    def track_all_assets(self):
        """Main tracking loop: fetch prices, analyze, send alerts."""
        db = SessionLocal()
        try:
            # Get USD/EUR rate for stock price conversion
            self._eur_rate = self.coingecko.get_usd_eur_rate()

            assets = db.query(Asset).filter(Asset.is_watchlist == True).all()
            logger.info(f"Tracking {len(assets)} assets...")

            for asset in assets:
                try:
                    self._track_asset(db, asset)
                except Exception as e:
                    logger.error(f"Error tracking {asset.symbol}: {e}")

            logger.info("Tracking cycle complete")
        except Exception as e:
            logger.error(f"Tracking error: {e}")
        finally:
            db.close()

    def _track_asset(self, db: Session, asset: Asset):
        """Track a single asset: fetch price, store, analyze, alert."""
        # ─── 1. Fetch current price ────────────────────
        price_data = None
        eur_rate = getattr(self, '_eur_rate', 0.92)
        if asset.asset_type == "crypto":
            price_data = self.coingecko.get_price(asset.coingecko_id or asset.symbol.lower())
        elif asset.asset_type == "stock":
            price_data = self.yahoo.get_price(asset.symbol, eur_rate=eur_rate)

        if not price_data:
            logger.warning(f"Could not fetch price for {asset.symbol}")
            return

        current_price = price_data["price"]

        # ─── 2. Store price ────────────────────────────
        ph = PriceHistory(
            asset_id=asset.id,
            price=current_price,
            volume=price_data.get("volume_24h"),
            market_cap=price_data.get("market_cap"),
        )
        db.add(ph)
        db.commit()
        logger.info(f"{asset.symbol}: €{current_price:,.2f}")

        # ─── 3. Get historical data for analysis ──────
        df = self._get_historical_data(asset)
        if df is None or len(df) < 30:
            logger.info(f"{asset.symbol}: Not enough historical data for analysis")
            return

        # ─── 4. Generate signal ────────────────────────
        signal_data = self.signal_gen.evaluate_asset(db, asset, df, current_price)
        if not signal_data:
            return

        analysis = signal_data.get("analysis", {})
        signal_type = analysis.get("signal", "HOLD")
        confidence = analysis.get("confidence", 0)

        # ─── 5. Check if alert should be sent ─────────
        if signal_type in ("HOLD",):
            return  # Don't alert on HOLD

        if confidence < SIGNAL_CONFIDENCE_MIN:
            logger.debug(f"{asset.symbol}: Confidence {confidence:.0f}% below threshold")
            return

        if not self.alert_mgr.should_send_alert(db, asset.id, signal_type):
            return

        # ─── 6. Save alert and send Telegram ──────────
        alert = self.signal_gen.save_alert(db, signal_data)
        if alert:
            msg = self.alert_mgr.format_alert_message(signal_data)
            try:
                asyncio.run(self.telegram.send_alert(msg))
                alert.sent_telegram = True
                db.commit()
                logger.info(f"Alert sent for {asset.symbol}: {signal_type}")
            except Exception as e:
                logger.error(f"Failed to send Telegram alert: {e}")

    def _get_historical_data(self, asset: Asset) -> pd.DataFrame:
        """Get historical OHLCV data for analysis."""
        try:
            if asset.asset_type == "crypto":
                # Use market_chart which gives daily granularity (90+ data points)
                chart = self.coingecko.get_market_chart(
                    asset.coingecko_id or asset.symbol.lower(),
                    days=90
                )
                if chart and chart["prices"]:
                    # Build DataFrame from market_chart prices
                    price_df = pd.DataFrame(chart["prices"])
                    price_df["timestamp"] = pd.to_datetime(price_df["timestamp"], unit="ms")
                    price_df.set_index("timestamp", inplace=True)
                    price_df = price_df.rename(columns={"price": "close"})

                    # Resample to daily candles
                    daily = price_df["close"].resample("1D").agg(
                        open="first", high="max", low="min", close="last"
                    ).dropna()

                    # Add volume data
                    if chart.get("volumes"):
                        vol_df = pd.DataFrame(chart["volumes"])
                        vol_df["timestamp"] = pd.to_datetime(vol_df["timestamp"], unit="ms")
                        vol_df.set_index("timestamp", inplace=True)
                        vol_daily = vol_df["volume"].resample("1D").sum()
                        daily["volume"] = vol_daily.reindex(daily.index, fill_value=0)
                    else:
                        daily["volume"] = 0

                    logger.info(f"{asset.symbol}: Got {len(daily)} daily data points for analysis")
                    return daily

            elif asset.asset_type == "stock":
                eur_rate = getattr(self, '_eur_rate', 0.92)
                return self.yahoo.get_historical(asset.symbol, period="3mo", interval="1d", eur_rate=eur_rate)

        except Exception as e:
            logger.error(f"Error fetching historical data for {asset.symbol}: {e}")

        return None

    def get_current_prices(self, db: Session) -> list:
        """Get current prices for all watchlist assets (in EUR)."""
        assets = db.query(Asset).filter(Asset.is_watchlist == True).all()
        results = []
        eur_rate = self.coingecko.get_usd_eur_rate()

        for asset in assets:
            price_data = None
            if asset.asset_type == "crypto":
                price_data = self.coingecko.get_price(asset.coingecko_id or asset.symbol.lower())
            elif asset.asset_type == "stock":
                price_data = self.yahoo.get_price(asset.symbol, eur_rate=eur_rate)

            if price_data:
                results.append({
                    "symbol": asset.symbol,
                    "name": asset.name,
                    "type": asset.asset_type,
                    "price": price_data["price"],
                    "change_24h": price_data.get("change_24h", 0),
                    "volume_24h": price_data.get("volume_24h", 0),
                    "market_cap": price_data.get("market_cap", 0),
                })

        return results

    def get_signals(self, db: Session) -> list:
        """Get current signals for all watched assets (in EUR)."""
        assets = db.query(Asset).filter(Asset.is_watchlist == True).all()
        results = []
        eur_rate = self.coingecko.get_usd_eur_rate()

        for asset in assets:
            try:
                # Get price (in EUR)
                price_data = None
                if asset.asset_type == "crypto":
                    price_data = self.coingecko.get_price(asset.coingecko_id or asset.symbol.lower())
                elif asset.asset_type == "stock":
                    price_data = self.yahoo.get_price(asset.symbol, eur_rate=eur_rate)

                if not price_data:
                    continue

                # Get historical
                df = self._get_historical_data(asset)
                if df is None or len(df) < 30:
                    continue

                # Generate signal
                signal_data = self.signal_gen.evaluate_asset(db, asset, df, price_data["price"])
                if signal_data:
                    results.append(signal_data)

            except Exception as e:
                logger.error(f"Error getting signal for {asset.symbol}: {e}")

        return results
