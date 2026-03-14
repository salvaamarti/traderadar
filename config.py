"""
TradeRadar - Configuration
"""
import os

# ─── Telegram ───────────────────────────────────────────────
TELEGRAM_ENABLED = True
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "7654108698:AAHzrNT8FfdAKNyR4lmha3p1BDoTUKVnvVo")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "1280006025")

# ─── Database ───────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///traderadar.db")

# ─── Price Tracking Intervals (seconds) ────────────────────
CRYPTO_INTERVAL_SECONDS = 300      # 5 minutes
STOCK_INTERVAL_SECONDS = 900       # 15 minutes
ANALYSIS_INTERVAL_SECONDS = 600    # 10 minutes

# ─── Analysis Thresholds ───────────────────────────────────
RSI_OVERSOLD = 30       # RSI below this → potential buy
RSI_OVERBOUGHT = 70     # RSI above this → potential sell
SIGNAL_CONFIDENCE_MIN = 60  # Minimum confidence to send alert (%)

# ─── Alert Settings ────────────────────────────────────────
ALERT_COOLDOWN_MINUTES = 60   # Min time between same alert
MAX_ALERTS_PER_HOUR = 10      # Rate limit

# ─── Currency ──────────────────────────────────────────────
DISPLAY_CURRENCY = "eur"  # All prices displayed in EUR

# ─── CoinGecko API ────────────────────────────────────────
COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"

# ─── Supported Crypto IDs (CoinGecko format) ──────────────
DEFAULT_WATCHLIST_CRYPTO = ["bitcoin"]
DEFAULT_WATCHLIST_STOCKS = []
