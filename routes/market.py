"""
TradeRadar - Market API Routes
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from database.db import get_db
from database.models import Asset, Alert, PortfolioEntry, PriceHistory
from services.price_tracker import PriceTracker
from services.coingecko import CoinGeckoClient
from services.yahoo_finance import YahooFinanceClient

router = APIRouter(prefix="/api/market", tags=["market"])
tracker = PriceTracker()
coingecko = CoinGeckoClient()
yahoo = YahooFinanceClient()


class WatchlistAdd(BaseModel):
    symbol: str
    name: str
    asset_type: Optional[str] = None  # "crypto" or "stock" (auto-detected if empty)
    coingecko_id: Optional[str] = None


@router.get("/prices")
def get_prices(db: Session = Depends(get_db)):
    """Get current prices for all watchlist assets."""
    return {"prices": tracker.get_current_prices(db)}


@router.get("/signals")
def get_signals(db: Session = Depends(get_db)):
    """Get current trading signals for all watched assets."""
    return {"signals": tracker.get_signals(db)}


@router.get("/watchlist")
def get_watchlist(db: Session = Depends(get_db)):
    """Get watchlist assets."""
    assets = db.query(Asset).filter(Asset.is_watchlist == True).all()
    return {
        "watchlist": [
            {
                "id": a.id,
                "symbol": a.symbol,
                "name": a.name,
                "asset_type": a.asset_type,
                "coingecko_id": a.coingecko_id,
            }
            for a in assets
        ]
    }


@router.post("/watchlist")
def add_to_watchlist(data: WatchlistAdd, db: Session = Depends(get_db)):
    """Add asset to watchlist."""
    existing = db.query(Asset).filter(Asset.symbol == data.symbol.upper()).first()
    if existing:
        existing.is_watchlist = True
        db.commit()
        return {"message": f"{data.symbol.upper()} already exists, re-added to watchlist"}

    # Auto-detect asset type if not provided
    asset_type = data.asset_type
    coingecko_id = data.coingecko_id

    if not asset_type:
        asset_type, coingecko_id = _detect_asset_type(data.symbol, coingecko_id)

    asset = Asset(
        symbol=data.symbol.upper(),
        name=data.name,
        asset_type=asset_type,
        coingecko_id=coingecko_id,
        is_watchlist=True,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)

    return {"message": f"{data.symbol.upper()} added to watchlist", "id": asset.id}


@router.delete("/watchlist/{symbol}")
def remove_from_watchlist(symbol: str, db: Session = Depends(get_db)):
    """Remove asset from watchlist and clean up if orphaned."""
    asset = db.query(Asset).filter(Asset.symbol == symbol.upper()).first()
    if not asset:
        raise HTTPException(status_code=404, detail=f"Asset {symbol} not found")

    asset.is_watchlist = False
    db.commit()

    # Clean up orphaned asset if it has no portfolio entries
    remaining_entries = db.query(PortfolioEntry).filter(PortfolioEntry.asset_id == asset.id).count()
    if remaining_entries == 0:
        db.query(PriceHistory).filter(PriceHistory.asset_id == asset.id).delete()
        db.query(Alert).filter(Alert.asset_id == asset.id).delete()
        db.delete(asset)
        db.commit()

    return {"message": f"{symbol.upper()} removed from watchlist"}


@router.get("/alerts")
def get_recent_alerts(limit: int = 20, db: Session = Depends(get_db)):
    """Get recent alerts."""
    alerts = (
        db.query(Alert)
        .order_by(Alert.created_at.desc())
        .limit(limit)
        .all()
    )

    result = []
    for alert in alerts:
        asset = db.query(Asset).filter(Asset.id == alert.asset_id).first()
        result.append({
            "id": alert.id,
            "symbol": asset.symbol if asset else "N/A",
            "signal_type": alert.signal_type,
            "confidence": alert.confidence,
            "current_price": alert.current_price,
            "message": alert.message,
            "sent_telegram": alert.sent_telegram,
            "created_at": alert.created_at.isoformat() if alert.created_at else None,
        })

    return {"alerts": result}


@router.post("/trigger-analysis")
def trigger_analysis(db: Session = Depends(get_db)):
    """Manually trigger analysis for all watched assets."""
    try:
        tracker.track_all_assets()
        return {"message": "Analysis triggered successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _detect_asset_type(symbol: str, coingecko_id: Optional[str] = None) -> tuple:
    """
    Auto-detect whether a symbol is a stock or crypto.
    Returns (asset_type, coingecko_id).
    Strategy: check CoinGecko first — if symbol matches a top crypto (rank <= 500),
    it's crypto. Otherwise default to stock.
    """
    import logging
    logger = logging.getLogger(__name__)

    # 1) Try CoinGecko search — only accept top 500 coins to avoid meme token false positives
    try:
        search = coingecko.search_coin(symbol)
        if search:
            for result in search:
                if result["symbol"].upper() == symbol.upper():
                    rank = result.get("market_cap_rank")
                    if rank and rank <= 500:
                        logger.info(f"Auto-detected {symbol} as CRYPTO (coingecko: {result['id']}, rank={rank})")
                        return ("crypto", result["id"])
                    else:
                        logger.info(f"Skipping CoinGecko match '{result['id']}' for {symbol} (rank={rank})")
    except Exception as e:
        logger.warning(f"CoinGecko search error for {symbol}: {e}")

    # 2) Not found as top crypto → assume stock
    logger.info(f"Auto-detected {symbol} as STOCK (not found as top crypto)")
    return ("stock", coingecko_id)


