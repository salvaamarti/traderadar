"""
TradeRadar - Portfolio API Routes
"""
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import case
from pydantic import BaseModel
from typing import Optional, List
from database.db import get_db
from database.models import Asset, PortfolioEntry, PriceHistory, Alert
from services.coingecko import CoinGeckoClient
from services.yahoo_finance import YahooFinanceClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


coingecko = CoinGeckoClient()
yahoo = YahooFinanceClient()


# ─── Pydantic Schemas ──────────────────────────────────────

class AssetCreate(BaseModel):
    symbol: str
    name: str
    asset_type: str  # "crypto" or "stock"
    coingecko_id: Optional[str] = None


class PortfolioEntryCreate(BaseModel):
    symbol: str
    name: Optional[str] = None
    asset_type: Optional[str] = None  # "crypto" or "stock"
    coingecko_id: Optional[str] = None
    quantity: float
    buy_price: float
    total_invested: Optional[float] = None
    notes: Optional[str] = None


class PortfolioEntryUpdate(BaseModel):
    quantity: float
    buy_price: float
    total_invested: Optional[float] = None
    notes: Optional[str] = None



class PortfolioSellRequest(BaseModel):
    symbol: str
    quantity: float
    sell_price: float


class PortfolioOrderUpdate(BaseModel):
    ordered_ids: List[int]

# ─── Routes ────────────────────────────────────────────────

@router.get("/")
def get_portfolio(db: Session = Depends(get_db)):
    """Get full portfolio with current prices and P&L."""
    entries = (
        db.query(PortfolioEntry)
        .filter(PortfolioEntry.sold == False)
        .order_by(PortfolioEntry.sort_order.asc())
        .all()
    )

    # Pre-fetch all crypto prices in a single API call to avoid rate limits
    crypto_assets = [db.query(Asset).filter(Asset.id == e.asset_id, Asset.asset_type == "crypto").first() for e in entries]
    crypto_ids = list(set([a.coingecko_id or a.symbol.lower() for a in crypto_assets if a]))
    if crypto_ids:
        coingecko.get_prices(crypto_ids)

    result = []
    total_invested = 0
    total_current_value = 0

    for entry in entries:
        asset = db.query(Asset).filter(Asset.id == entry.asset_id).first()
        if not asset:
            continue

        # Get current price
        current_price = _get_current_price(asset)
        current_value = entry.quantity * current_price
        pnl = current_value - entry.total_invested
        pnl_pct = ((current_price - entry.buy_price) / entry.buy_price * 100) if entry.buy_price > 0 else 0

        total_invested += entry.total_invested
        total_current_value += current_value

        result.append({
            "id": entry.id,
            "symbol": asset.symbol,
            "name": asset.name,
            "asset_type": asset.asset_type,
            "quantity": entry.quantity,
            "buy_price": entry.buy_price,
            "total_invested": entry.total_invested,
            "current_price": current_price,
            "current_value": round(current_value, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "buy_date": entry.buy_date.isoformat() if entry.buy_date else None,
            "notes": entry.notes,
        })

    return {
        "entries": result,
        "summary": {
            "total_invested": round(total_invested, 2),
            "total_current_value": round(total_current_value, 2),
            "total_pnl": round(total_current_value - total_invested, 2),
            "total_pnl_pct": round(
                ((total_current_value - total_invested) / total_invested * 100)
                if total_invested > 0 else 0, 2
            ),
        },
    }


@router.post("/buy")
def add_buy(data: PortfolioEntryCreate, db: Session = Depends(get_db)):
    """Register a purchase (manual entry)."""
    logger.info(f"[BUY] symbol={data.symbol}, asset_type={data.asset_type!r}, coingecko_id={data.coingecko_id!r}")
    # Find or create asset
    asset = db.query(Asset).filter(Asset.symbol == data.symbol.upper()).first()
    if not asset:
        # Use explicit type if provided, otherwise auto-detect
        asset_type = data.asset_type
        coingecko_id = data.coingecko_id

        if not asset_type:
            # Auto-detect: check CoinGecko first (crypto), otherwise assume stock
            # (Yahoo Finance .info/.fast_info are unreliable due to rate limits)
            # Only accept CoinGecko matches with market_cap_rank <= 500 to avoid
            # false positives from obscure meme tokens sharing stock tickers
            try:
                search = coingecko.search_coin(data.symbol)
                if search:
                    for result in search:
                        if result["symbol"].upper() == data.symbol.upper():
                            rank = result.get("market_cap_rank")
                            if rank and rank <= 500:
                                coingecko_id = result["id"]
                                asset_type = "crypto"
                                logger.info(f"[AUTO-DETECT] {data.symbol} → CRYPTO (coingecko_id={coingecko_id}, rank={rank})")
                                break
                            else:
                                logger.info(f"[AUTO-DETECT] Skipping CoinGecko match '{result['id']}' for {data.symbol} (rank={rank})")
            except Exception as e:
                logger.warning(f"[AUTO-DETECT] CoinGecko search failed for {data.symbol}: {e}")

            if not asset_type:
                asset_type = "stock"
                logger.info(f"[AUTO-DETECT] {data.symbol} → STOCK (not found as top crypto)")

        asset = Asset(
            symbol=data.symbol.upper(),
            name=data.name or data.symbol.upper(),
            asset_type=asset_type,
            coingecko_id=coingecko_id,
            is_watchlist=True,
        )
        db.add(asset)
        db.commit()
        db.refresh(asset)

    total_invested = data.total_invested or (data.quantity * data.buy_price)

    entry = PortfolioEntry(
        asset_id=asset.id,
        quantity=data.quantity,
        buy_price=data.buy_price,
        total_invested=total_invested,
        notes=data.notes,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    return {
        "message": f"Compra registrada: {data.quantity} {data.symbol.upper()} a €{data.buy_price:,.2f}",
        "entry_id": entry.id,
        "total_invested": total_invested,
    }


@router.post("/sell")
def register_sell(data: PortfolioSellRequest, db: Session = Depends(get_db)):
    """Register a sale."""
    asset = db.query(Asset).filter(Asset.symbol == data.symbol.upper()).first()
    if not asset:
        raise HTTPException(status_code=404, detail=f"Asset {data.symbol} not found")

    entries = (
        db.query(PortfolioEntry)
        .filter(PortfolioEntry.asset_id == asset.id, PortfolioEntry.sold == False)
        .order_by(PortfolioEntry.buy_date.asc())
        .all()
    )

    if not entries:
        raise HTTPException(status_code=400, detail=f"No open positions for {data.symbol}")

    remaining_qty = data.quantity
    total_pnl = 0

    for entry in entries:
        if remaining_qty <= 0:
            break

        if entry.quantity <= remaining_qty:
            # Sell entire entry
            entry.sold = True
            entry.sell_price = data.sell_price
            entry.sell_date = datetime.utcnow()
            pnl = (data.sell_price - entry.buy_price) * entry.quantity
            total_pnl += pnl
            remaining_qty -= entry.quantity
        else:
            # Partial sell: split entry
            sold_entry = PortfolioEntry(
                asset_id=asset.id,
                quantity=remaining_qty,
                buy_price=entry.buy_price,
                total_invested=entry.buy_price * remaining_qty,
                buy_date=entry.buy_date,
                sold=True,
                sell_price=data.sell_price,
                sell_date=datetime.utcnow(),
            )
            entry.quantity -= remaining_qty
            entry.total_invested = entry.buy_price * entry.quantity
            pnl = (data.sell_price - entry.buy_price) * remaining_qty
            total_pnl += pnl
            db.add(sold_entry)
            remaining_qty = 0

    db.commit()

    return {
        "message": f"Venta registrada: {data.quantity} {data.symbol.upper()} a €{data.sell_price:,.2f}",
        "pnl": round(total_pnl, 2),
        "remaining_qty_unsold": remaining_qty,
    }


@router.get("/history")
def get_history(db: Session = Depends(get_db)):
    """Get portfolio history (sold entries)."""
    entries = (
        db.query(PortfolioEntry)
        .filter(PortfolioEntry.sold == True)
        .order_by(PortfolioEntry.sell_date.desc())
        .all()
    )

    result = []
    for entry in entries:
        asset = db.query(Asset).filter(Asset.id == entry.asset_id).first()
        if not asset:
            continue
        pnl = (entry.sell_price - entry.buy_price) * entry.quantity if entry.sell_price else 0
        result.append({
            "symbol": asset.symbol,
            "name": asset.name,
            "quantity": entry.quantity,
            "buy_price": entry.buy_price,
            "sell_price": entry.sell_price,
            "pnl": round(pnl, 2),
            "buy_date": entry.buy_date.isoformat() if entry.buy_date else None,
            "sell_date": entry.sell_date.isoformat() if entry.sell_date else None,
        })

    return {"history": result}


@router.delete("/{entry_id}")
def delete_entry(entry_id: int, db: Session = Depends(get_db)):
    """Delete a portfolio entry and clean up orphaned assets."""
    entry = db.query(PortfolioEntry).filter(PortfolioEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    asset_id = entry.asset_id
    db.delete(entry)
    db.commit()

    # Clean up orphaned asset if it's no longer in portfolio or watchlist
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if asset and not asset.is_watchlist:
        remaining_entries = db.query(PortfolioEntry).filter(PortfolioEntry.asset_id == asset_id).count()
        if remaining_entries == 0:
            db.query(PriceHistory).filter(PriceHistory.asset_id == asset_id).delete()
            db.query(Alert).filter(Alert.asset_id == asset_id).delete()
            db.delete(asset)
            db.commit()
            logger.info(f"Deleted orphaned asset: {asset.symbol}")

    return {"message": "Entry deleted"}


@router.put("/order")
def update_portfolio_order(data: PortfolioOrderUpdate, db: Session = Depends(get_db)):
    """Update sort_order for multiple portfolio entries."""
    if not data.ordered_ids:
        return {"message": "Sin cambios en el orden"}

    # Use CASE statement to bulk update sort_order efficiently
    case_stmt = case(
         {entry_id: idx for idx, entry_id in enumerate(data.ordered_ids)},
         value=PortfolioEntry.id
    )

    db.query(PortfolioEntry).filter(
        PortfolioEntry.id.in_(data.ordered_ids)
    ).update(
        {"sort_order": case_stmt},
        synchronize_session=False
    )
    db.commit()

    return {"message": "Orden actualizado"}


@router.put("/{entry_id}")
def update_entry(entry_id: int, data: PortfolioEntryUpdate, db: Session = Depends(get_db)):
    """Update a portfolio entry."""
    entry = db.query(PortfolioEntry).filter(PortfolioEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    entry.quantity = data.quantity
    entry.buy_price = data.buy_price
    entry.notes = data.notes

    if data.total_invested is not None:
        entry.total_invested = data.total_invested
    else:
        entry.total_invested = data.quantity * data.buy_price

    db.commit()
    db.refresh(entry)

    return {"message": "Posición actualizada"}





def _get_current_price(asset: Asset) -> float:
    """Helper to get current price for an asset (in EUR)."""
    try:
        if asset.asset_type == "crypto":
            data = coingecko.get_price(asset.coingecko_id or asset.symbol.lower())
        else:
            eur_rate = coingecko.get_usd_eur_rate()
            data = yahoo.get_price(asset.symbol, eur_rate=eur_rate)
        return data["price"] if data else 0
    except Exception:
        return 0
