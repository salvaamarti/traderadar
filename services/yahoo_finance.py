"""
TradeRadar - Yahoo Finance Client
Free stock price data via yfinance library.
"""
import yfinance as yf
import pandas as pd
import logging
from typing import Optional
from services.cache import price_cache, historical_cache

logger = logging.getLogger(__name__)


class YahooFinanceClient:
    """Client for Yahoo Finance data via yfinance."""

    def get_price(self, symbol: str, eur_rate: float = 1.0) -> Optional[dict]:
        """Get current price info for a stock, converted to EUR (cached 2 min)."""
        cache_key = f"yf_price:{symbol}:{eur_rate:.4f}"
        cached = price_cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            ticker = yf.Ticker(symbol)
            info = ticker.fast_info

            # Prevent double conversion if already priced in EUR
            currency = info.get("currency", "USD")
            multiplier = 1.0 if currency == "EUR" else eur_rate

            price = float(info.get("lastPrice", 0) or info.get("previousClose", 0)) * multiplier
            market_cap = float(info.get("marketCap", 0)) * multiplier

            result = {
                "price": price,
                "volume_24h": float(info.get("lastVolume", 0)),
                "market_cap": market_cap,
                "change_24h": float(
                    ((info.get("lastPrice", 0) - info.get("previousClose", 0))
                     / info.get("previousClose", 1)) * 100
                ) if info.get("previousClose") else 0,
            }
            price_cache.set(cache_key, result)
            return result
        except Exception as e:
            logger.error(f"Yahoo Finance price error for {symbol}: {e}")
            return None

    def get_historical(self, symbol: str, period: str = "3mo", interval: str = "1d", eur_rate: float = 1.0) -> Optional[pd.DataFrame]:
        """
        Get historical OHLCV data (cached 30 min).
        period: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max
        interval: 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo
        """
        cache_key = f"yf_hist:{symbol}:{period}:{interval}:{eur_rate:.4f}"
        cached = historical_cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            ticker = yf.Ticker(symbol)
            info = ticker.fast_info
            
            # Prevent double conversion if already priced in EUR
            currency = info.get("currency", "USD")
            multiplier = 1.0 if currency == "EUR" else eur_rate

            df = ticker.history(period=period, interval=interval)

            if df.empty:
                logger.warning(f"No historical data for {symbol}")
                return None

            df.index = pd.to_datetime(df.index)
            df = df.rename(columns={
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume"
            })

            # Convert price columns to EUR
            if multiplier != 1.0:
                for col in ["open", "high", "low", "close"]:
                    df[col] = df[col] * multiplier

            result = df[["open", "high", "low", "close", "volume"]]
            historical_cache.set(cache_key, result)
            return result
        except Exception as e:
            logger.error(f"Yahoo Finance historical error for {symbol}: {e}")
            return None

    def get_info(self, symbol: str) -> Optional[dict]:
        """Get full stock info."""
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            return {
                "symbol": symbol.upper(),
                "name": info.get("longName", info.get("shortName", symbol)),
                "sector": info.get("sector", "N/A"),
                "industry": info.get("industry", "N/A"),
                "currency": info.get("currency", "USD"),
            }
        except Exception as e:
            logger.error(f"Yahoo Finance info error for {symbol}: {e}")
            return None

    def ping(self) -> bool:
        """Check if Yahoo Finance is accessible."""
        try:
            ticker = yf.Ticker("AAPL")
            _ = ticker.fast_info
            return True
        except Exception:
            return False
