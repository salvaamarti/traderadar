"""
TradeRadar - Database Models
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Enum, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from database.db import Base
import enum


class AssetType(str, enum.Enum):
    CRYPTO = "crypto"
    STOCK = "stock"


class SignalType(str, enum.Enum):
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"


class Asset(Base):
    __tablename__ = "assets"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, unique=True, nullable=False, index=True)        # BTC, AAPL
    name = Column(String, nullable=False)                                   # Bitcoin, Apple Inc.
    asset_type = Column(String, nullable=False)                             # crypto / stock
    coingecko_id = Column(String, nullable=True)                            # bitcoin, ethereum...
    is_watchlist = Column(Boolean, default=True)                            # Track this asset?
    created_at = Column(DateTime, default=datetime.utcnow)

    portfolio_entries = relationship("PortfolioEntry", back_populates="asset")
    price_history = relationship("PriceHistory", back_populates="asset")
    alerts = relationship("Alert", back_populates="asset")


class PortfolioEntry(Base):
    __tablename__ = "portfolio_entries"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False)
    quantity = Column(Float, nullable=False)                                # Amount bought
    buy_price = Column(Float, nullable=False)                               # Price per unit at purchase
    total_invested = Column(Float, nullable=False)                          # Total money invested
    buy_date = Column(DateTime, default=datetime.utcnow)
    sold = Column(Boolean, default=False)                                   # Has been sold?
    sell_price = Column(Float, nullable=True)                               # Sell price per unit
    sell_date = Column(DateTime, nullable=True)
    notes = Column(String, nullable=True)
    sort_order = Column(Integer, default=0)                                 # Custom sorting order

    asset = relationship("Asset", back_populates="portfolio_entries")


class PriceHistory(Base):
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False)
    price = Column(Float, nullable=False)
    volume = Column(Float, nullable=True)
    high_24h = Column(Float, nullable=True)
    low_24h = Column(Float, nullable=True)
    market_cap = Column(Float, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    asset = relationship("Asset", back_populates="price_history")


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False)
    signal_type = Column(String, nullable=False)                            # STRONG_BUY, BUY, etc.
    confidence = Column(Float, nullable=False)                              # 0-100
    current_price = Column(Float, nullable=False)
    message = Column(String, nullable=False)
    details = Column(String, nullable=True)                                 # JSON with indicator details
    sent_telegram = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    asset = relationship("Asset", back_populates="alerts")
