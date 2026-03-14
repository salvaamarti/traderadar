"""
TradeRadar - Main Application
FastAPI entry point with scheduler for automated tracking.
"""
import sys
import os
import logging
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from apscheduler.schedulers.background import BackgroundScheduler

from database.db import init_db, SessionLocal
from database.models import Asset
from routes.portfolio import router as portfolio_router
from routes.market import router as market_router
from services.price_tracker import PriceTracker
from services.telegram_bot import TelegramService
from config import (
    CRYPTO_INTERVAL_SECONDS,
    STOCK_INTERVAL_SECONDS,
    DEFAULT_WATCHLIST_CRYPTO,
    TELEGRAM_ENABLED,
)

# ─── Logging Config ────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("traderadar")

# ─── Services ──────────────────────────────────────────────
price_tracker = PriceTracker()
telegram = TelegramService()
scheduler = BackgroundScheduler()


def init_default_assets():
    """Initialize default watchlist assets if DB is empty."""
    db = SessionLocal()
    try:
        existing = db.query(Asset).count()
        if existing == 0:
            for crypto_id in DEFAULT_WATCHLIST_CRYPTO:
                asset = Asset(
                    symbol=crypto_id.upper()[:3] if len(crypto_id) > 3 else crypto_id.upper(),
                    name=crypto_id.capitalize(),
                    asset_type="crypto",
                    coingecko_id=crypto_id,
                    is_watchlist=True,
                )
                # Special handling for known cryptos
                if crypto_id == "bitcoin":
                    asset.symbol = "BTC"
                    asset.name = "Bitcoin"
                elif crypto_id == "ethereum":
                    asset.symbol = "ETH"
                    asset.name = "Ethereum"

                db.add(asset)

            db.commit()
            logger.info(f"Initialized {len(DEFAULT_WATCHLIST_CRYPTO)} default crypto assets")
    except Exception as e:
        logger.error(f"Error initializing default assets: {e}")
        db.rollback()
    finally:
        db.close()


def scheduled_tracking():
    """Scheduled task for price tracking and analysis."""
    logger.info("⏰ Running scheduled tracking...")
    try:
        price_tracker.track_all_assets()
    except Exception as e:
        logger.error(f"Scheduled tracking error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown."""
    # ─── Startup ───────────────────────────────────────
    logger.info("🚀 TradeRadar starting up...")

    # Initialize database
    init_db()
    logger.info("✅ Database initialized")

    # Initialize default assets
    init_default_assets()

    # Test Telegram connection
    if TELEGRAM_ENABLED:
        try:
            connected = await telegram.test_connection()
            if connected:
                logger.info("✅ Telegram bot connected")
                await telegram.send_startup_message()
            else:
                logger.warning("⚠️ Telegram connection failed")
        except Exception as e:
            logger.warning(f"⚠️ Telegram startup error: {e}")

    # Start scheduler
    scheduler.add_job(
        scheduled_tracking,
        "interval",
        seconds=CRYPTO_INTERVAL_SECONDS,
        id="price_tracking",
        max_instances=1,
    )
    scheduler.start()
    logger.info(f"✅ Scheduler started (interval: {CRYPTO_INTERVAL_SECONDS}s)")

    # Run initial tracking
    logger.info("📡 Running initial price scan...")
    try:
        scheduled_tracking()
    except Exception as e:
        logger.warning(f"Initial tracking error: {e}")

    logger.info("🟢 TradeRadar is LIVE!")

    yield

    # ─── Shutdown ──────────────────────────────────────
    logger.info("🔴 TradeRadar shutting down...")
    scheduler.shutdown(wait=False)


# ─── FastAPI App ───────────────────────────────────────────
app = FastAPI(
    title="TradeRadar",
    description="Trading Alert System with Real-Time Price Tracking & Technical Analysis",
    version="1.0.0",
    lifespan=lifespan,
)

# ─── Mount Routes ──────────────────────────────────────────
app.include_router(portfolio_router)
app.include_router(market_router)

# ─── Static Files ──────────────────────────────────────────
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def root():
    """Serve the dashboard."""
    return FileResponse(os.path.join(static_dir, "index.html"))


@app.get("/api/status")
async def get_status():
    """System status endpoint."""
    return {
        "status": "running",
        "version": "1.0.0",
        "scheduler_running": scheduler.running,
        "telegram_enabled": TELEGRAM_ENABLED,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
