"""
TradeRadar - Technical Analysis Engine
Advanced multi-indicator analysis for generating buy/sell signals.
Uses RSI, MACD, Bollinger Bands, SMA/EMA crossovers, and volume analysis.
"""
import pandas as pd
import numpy as np
import ta
import logging
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class IndicatorResult:
    """Result from a single indicator."""
    name: str
    signal: str        # BUY, SELL, HOLD
    value: float       # Current indicator value
    strength: float    # -1.0 (strong sell) to +1.0 (strong buy)
    description: str


@dataclass
class AnalysisResult:
    """Combined analysis result for an asset."""
    symbol: str
    current_price: float
    signal: str             # STRONG_BUY, BUY, HOLD, SELL, STRONG_SELL
    confidence: float       # 0-100
    indicators: list = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "current_price": self.current_price,
            "signal": self.signal,
            "confidence": round(self.confidence, 1),
            "summary": self.summary,
            "indicators": [
                {
                    "name": ind.name,
                    "signal": ind.signal,
                    "value": round(ind.value, 4),
                    "strength": round(ind.strength, 4),
                    "description": ind.description,
                }
                for ind in self.indicators
            ],
        }


class TechnicalAnalyzer:
    """
    Multi-indicator technical analysis engine.

    Combines 6 indicators with weighted scoring:
    - RSI (20%): Relative Strength Index
    - MACD (25%): Moving Average Convergence Divergence
    - Bollinger Bands (20%): Volatility bands
    - SMA Crossover (15%): 20/50 period Simple Moving Average cross
    - EMA Trend (10%): Exponential Moving Average direction
    - Volume (10%): Volume trend confirmation
    """

    WEIGHTS = {
        "rsi": 0.20,
        "macd": 0.25,
        "bollinger": 0.20,
        "sma_cross": 0.15,
        "ema_trend": 0.10,
        "volume": 0.10,
    }

    def analyze(self, df: pd.DataFrame, symbol: str = "") -> Optional[AnalysisResult]:
        """
        Run full technical analysis on OHLCV data.

        Args:
            df: DataFrame with columns [open, high, low, close, volume] and DateTime index
            symbol: Asset symbol for labeling

        Returns:
            AnalysisResult with combined signal and individual indicators
        """
        if df is None or len(df) < 30:
            logger.warning(f"Insufficient data for analysis ({symbol}): need 30+ rows")
            return None

        try:
            close = df["close"]
            high = df["high"]
            low = df["low"]
            volume = df["volume"] if "volume" in df.columns else pd.Series(0, index=df.index)
            current_price = float(close.iloc[-1])

            indicators = []

            # ─── RSI ────────────────────────────────────────
            rsi_result = self._analyze_rsi(close)
            if rsi_result:
                indicators.append(rsi_result)

            # ─── MACD ───────────────────────────────────────
            macd_result = self._analyze_macd(close)
            if macd_result:
                indicators.append(macd_result)

            # ─── Bollinger Bands ────────────────────────────
            bb_result = self._analyze_bollinger(close)
            if bb_result:
                indicators.append(bb_result)

            # ─── SMA Crossover ──────────────────────────────
            sma_result = self._analyze_sma_crossover(close)
            if sma_result:
                indicators.append(sma_result)

            # ─── EMA Trend ──────────────────────────────────
            ema_result = self._analyze_ema_trend(close)
            if ema_result:
                indicators.append(ema_result)

            # ─── Volume ─────────────────────────────────────
            vol_result = self._analyze_volume(close, volume)
            if vol_result:
                indicators.append(vol_result)

            # ─── Combine signals ────────────────────────────
            signal, confidence = self._combine_signals(indicators)
            summary = self._generate_summary(indicators, signal, confidence)

            return AnalysisResult(
                symbol=symbol,
                current_price=current_price,
                signal=signal,
                confidence=confidence,
                indicators=indicators,
                summary=summary,
            )

        except Exception as e:
            logger.error(f"Analysis error for {symbol}: {e}")
            return None

    def _analyze_rsi(self, close: pd.Series) -> Optional[IndicatorResult]:
        """Relative Strength Index (14 periods)."""
        try:
            rsi = ta.momentum.RSIIndicator(close, window=14).rsi()
            current_rsi = float(rsi.iloc[-1])

            if np.isnan(current_rsi):
                return None

            if current_rsi <= 20:
                signal, strength = "BUY", 1.0
                desc = f"RSI={current_rsi:.1f} → Muy sobrevendido, fuerte señal de compra"
            elif current_rsi <= 30:
                signal, strength = "BUY", 0.7
                desc = f"RSI={current_rsi:.1f} → Sobrevendido, posible rebote"
            elif current_rsi <= 45:
                signal, strength = "BUY", 0.3
                desc = f"RSI={current_rsi:.1f} → Zona baja, tendencia a subir"
            elif current_rsi <= 55:
                signal, strength = "HOLD", 0.0
                desc = f"RSI={current_rsi:.1f} → Zona neutral"
            elif current_rsi <= 70:
                signal, strength = "SELL", -0.3
                desc = f"RSI={current_rsi:.1f} → Zona alta, posible corrección"
            elif current_rsi <= 80:
                signal, strength = "SELL", -0.7
                desc = f"RSI={current_rsi:.1f} → Sobrecomprado, señal de venta"
            else:
                signal, strength = "SELL", -1.0
                desc = f"RSI={current_rsi:.1f} → Muy sobrecomprado, fuerte señal de venta"

            return IndicatorResult("RSI", signal, current_rsi, strength, desc)
        except Exception as e:
            logger.error(f"RSI analysis error: {e}")
            return None

    def _analyze_macd(self, close: pd.Series) -> Optional[IndicatorResult]:
        """MACD with signal line crossover detection."""
        try:
            macd_obj = ta.trend.MACD(close, window_slow=26, window_fast=12, window_sign=9)
            macd_line = macd_obj.macd()
            signal_line = macd_obj.macd_signal()
            histogram = macd_obj.macd_diff()

            current_macd = float(macd_line.iloc[-1])
            current_signal = float(signal_line.iloc[-1])
            current_hist = float(histogram.iloc[-1])
            prev_hist = float(histogram.iloc[-2]) if len(histogram) > 1 else 0

            if np.isnan(current_macd) or np.isnan(current_signal):
                return None

            # Crossover detection
            crossover_bullish = prev_hist <= 0 and current_hist > 0
            crossover_bearish = prev_hist >= 0 and current_hist < 0

            if crossover_bullish:
                signal, strength = "BUY", 0.9
                desc = f"MACD cruce alcista ↑ Histograma={current_hist:.4f}"
            elif crossover_bearish:
                signal, strength = "SELL", -0.9
                desc = f"MACD cruce bajista ↓ Histograma={current_hist:.4f}"
            elif current_hist > 0 and current_hist > prev_hist:
                signal, strength = "BUY", 0.5
                desc = f"MACD positivo y creciente, momento alcista"
            elif current_hist > 0 and current_hist <= prev_hist:
                signal, strength = "HOLD", 0.2
                desc = f"MACD positivo pero decreciente, momento debilitándose"
            elif current_hist < 0 and current_hist < prev_hist:
                signal, strength = "SELL", -0.5
                desc = f"MACD negativo y decreciente, momento bajista"
            elif current_hist < 0 and current_hist >= prev_hist:
                signal, strength = "HOLD", -0.2
                desc = f"MACD negativo pero recuperándose"
            else:
                signal, strength = "HOLD", 0.0
                desc = "MACD neutral"

            return IndicatorResult("MACD", signal, current_hist, strength, desc)
        except Exception as e:
            logger.error(f"MACD analysis error: {e}")
            return None

    def _analyze_bollinger(self, close: pd.Series) -> Optional[IndicatorResult]:
        """Bollinger Bands (20 periods, 2 std dev)."""
        try:
            bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
            upper = float(bb.bollinger_hband().iloc[-1])
            lower = float(bb.bollinger_lband().iloc[-1])
            middle = float(bb.bollinger_mavg().iloc[-1])
            pband = float(bb.bollinger_pband().iloc[-1])  # %B indicator

            current_price = float(close.iloc[-1])

            if np.isnan(pband):
                return None

            if pband <= 0:
                signal, strength = "BUY", 0.9
                desc = f"Precio por debajo de banda inferior (%%B={pband:.2f}), rebote probable"
            elif pband <= 0.2:
                signal, strength = "BUY", 0.6
                desc = f"Precio cerca de banda inferior (%%B={pband:.2f}), zona de compra"
            elif pband <= 0.4:
                signal, strength = "BUY", 0.2
                desc = f"Precio en zona baja de Bollinger (%%B={pband:.2f})"
            elif pband <= 0.6:
                signal, strength = "HOLD", 0.0
                desc = f"Precio en zona media de Bollinger (%%B={pband:.2f})"
            elif pband <= 0.8:
                signal, strength = "SELL", -0.2
                desc = f"Precio en zona alta de Bollinger (%%B={pband:.2f})"
            elif pband < 1.0:
                signal, strength = "SELL", -0.6
                desc = f"Precio cerca de banda superior (%%B={pband:.2f}), zona de venta"
            else:
                signal, strength = "SELL", -0.9
                desc = f"Precio por encima de banda superior (%%B={pband:.2f}), corrección probable"

            return IndicatorResult("Bollinger Bands", signal, pband, strength, desc)
        except Exception as e:
            logger.error(f"Bollinger analysis error: {e}")
            return None

    def _analyze_sma_crossover(self, close: pd.Series) -> Optional[IndicatorResult]:
        """SMA 20/50 crossover (golden cross / death cross)."""
        try:
            sma_short = ta.trend.SMAIndicator(close, window=20).sma_indicator()
            sma_long = ta.trend.SMAIndicator(close, window=50).sma_indicator()

            current_short = float(sma_short.iloc[-1])
            current_long = float(sma_long.iloc[-1])

            if np.isnan(current_short) or np.isnan(current_long):
                return None

            # Check for recent crossover
            prev_short = float(sma_short.iloc[-2])
            prev_long = float(sma_long.iloc[-2])

            golden_cross = prev_short <= prev_long and current_short > current_long
            death_cross = prev_short >= prev_long and current_short < current_long

            ratio = (current_short - current_long) / current_long

            if golden_cross:
                signal, strength = "BUY", 0.9
                desc = f"¡Cruz Dorada! SMA20 cruza por encima de SMA50"
            elif death_cross:
                signal, strength = "SELL", -0.9
                desc = f"¡Cruz de Muerte! SMA20 cruza por debajo de SMA50"
            elif ratio > 0.03:
                signal, strength = "BUY", 0.5
                desc = f"SMA20 > SMA50 (+{ratio*100:.1f}%), tendencia alcista"
            elif ratio > 0:
                signal, strength = "BUY", 0.2
                desc = f"SMA20 ligeramente por encima de SMA50, alcista débil"
            elif ratio > -0.03:
                signal, strength = "SELL", -0.2
                desc = f"SMA20 ligeramente por debajo de SMA50, bajista débil"
            else:
                signal, strength = "SELL", -0.5
                desc = f"SMA20 < SMA50 ({ratio*100:.1f}%), tendencia bajista"

            return IndicatorResult("SMA Cross", signal, ratio, strength, desc)
        except Exception as e:
            logger.error(f"SMA crossover analysis error: {e}")
            return None

    def _analyze_ema_trend(self, close: pd.Series) -> Optional[IndicatorResult]:
        """EMA 12 trend direction."""
        try:
            ema = ta.trend.EMAIndicator(close, window=12).ema_indicator()

            if len(ema) < 5:
                return None

            current_ema = float(ema.iloc[-1])
            ema_5_ago = float(ema.iloc[-5])

            if np.isnan(current_ema) or np.isnan(ema_5_ago):
                return None

            trend = (current_ema - ema_5_ago) / ema_5_ago
            current_price = float(close.iloc[-1])
            price_vs_ema = (current_price - current_ema) / current_ema

            if trend > 0.02 and price_vs_ema > 0:
                signal, strength = "BUY", 0.6
                desc = f"EMA12 tendencia alcista (+{trend*100:.2f}%), precio por encima"
            elif trend > 0:
                signal, strength = "BUY", 0.2
                desc = f"EMA12 ligeramente alcista (+{trend*100:.2f}%)"
            elif trend > -0.02:
                signal, strength = "SELL", -0.2
                desc = f"EMA12 ligeramente bajista ({trend*100:.2f}%)"
            else:
                signal, strength = "SELL", -0.6
                desc = f"EMA12 tendencia bajista ({trend*100:.2f}%), precio por debajo"

            return IndicatorResult("EMA Trend", signal, trend, strength, desc)
        except Exception as e:
            logger.error(f"EMA trend analysis error: {e}")
            return None

    def _analyze_volume(self, close: pd.Series, volume: pd.Series) -> Optional[IndicatorResult]:
        """Volume trend analysis."""
        try:
            if volume.sum() == 0:
                return IndicatorResult("Volume", "HOLD", 0, 0.0, "Sin datos de volumen")

            avg_volume_20 = float(volume.tail(20).mean())
            current_volume = float(volume.iloc[-1])
            price_change = float((close.iloc[-1] - close.iloc[-2]) / close.iloc[-2])

            if avg_volume_20 == 0:
                return IndicatorResult("Volume", "HOLD", 0, 0.0, "Volumen insuficiente")

            volume_ratio = current_volume / avg_volume_20

            # High volume + price up = bullish confirmation
            if volume_ratio > 1.5 and price_change > 0:
                signal, strength = "BUY", 0.7
                desc = f"Volumen alto ({volume_ratio:.1f}x promedio) + precio ↑, confirmación alcista"
            elif volume_ratio > 1.5 and price_change < 0:
                signal, strength = "SELL", -0.7
                desc = f"Volumen alto ({volume_ratio:.1f}x promedio) + precio ↓, confirmación bajista"
            elif volume_ratio > 1.2 and price_change > 0:
                signal, strength = "BUY", 0.3
                desc = f"Volumen por encima del promedio + precio ↑"
            elif volume_ratio > 1.2 and price_change < 0:
                signal, strength = "SELL", -0.3
                desc = f"Volumen por encima del promedio + precio ↓"
            else:
                signal, strength = "HOLD", 0.0
                desc = f"Volumen normal ({volume_ratio:.1f}x promedio)"

            return IndicatorResult("Volume", signal, volume_ratio, strength, desc)
        except Exception as e:
            logger.error(f"Volume analysis error: {e}")
            return None

    def _combine_signals(self, indicators: list) -> tuple:
        """
        Combine all indicator signals into a final signal with confidence.

        Returns:
            (signal_str, confidence_float)
        """
        if not indicators:
            return "HOLD", 0.0

        # Map indicator names to weight keys
        name_to_key = {
            "RSI": "rsi",
            "MACD": "macd",
            "Bollinger Bands": "bollinger",
            "SMA Cross": "sma_cross",
            "EMA Trend": "ema_trend",
            "Volume": "volume",
        }

        weighted_sum = 0.0
        total_weight = 0.0

        for ind in indicators:
            key = name_to_key.get(ind.name, "")
            weight = self.WEIGHTS.get(key, 0.1)
            weighted_sum += ind.strength * weight
            total_weight += weight

        if total_weight == 0:
            return "HOLD", 0.0

        # Normalize
        combined_score = weighted_sum / total_weight  # -1.0 to +1.0

        # Map to signal
        if combined_score >= 0.6:
            signal = "STRONG_BUY"
        elif combined_score >= 0.25:
            signal = "BUY"
        elif combined_score >= -0.25:
            signal = "HOLD"
        elif combined_score >= -0.6:
            signal = "SELL"
        else:
            signal = "STRONG_SELL"

        # Confidence: how strong is the consensus (0-100)
        confidence = abs(combined_score) * 100

        return signal, min(confidence, 100.0)

    def _generate_summary(self, indicators: list, signal: str, confidence: float) -> str:
        """Generate human-readable summary."""
        signal_emoji = {
            "STRONG_BUY": "🟢🟢",
            "BUY": "🟢",
            "HOLD": "🟡",
            "SELL": "🔴",
            "STRONG_SELL": "🔴🔴",
        }

        signal_text = {
            "STRONG_BUY": "COMPRA FUERTE",
            "BUY": "COMPRA",
            "HOLD": "MANTENER",
            "SELL": "VENTA",
            "STRONG_SELL": "VENTA FUERTE",
        }

        emoji = signal_emoji.get(signal, "⚪")
        text = signal_text.get(signal, signal)

        buy_count = sum(1 for i in indicators if i.signal == "BUY")
        sell_count = sum(1 for i in indicators if i.signal == "SELL")
        hold_count = sum(1 for i in indicators if i.signal == "HOLD")

        summary = (
            f"{emoji} {text} (confianza: {confidence:.0f}%)\n"
            f"📊 Indicadores: {buy_count} compra / {hold_count} neutral / {sell_count} venta"
        )

        return summary
