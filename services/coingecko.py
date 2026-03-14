"""
TradeRadar - CoinGecko API Client
Free API for cryptocurrency price data.
"""
import requests
import logging
from typing import Optional
from config import COINGECKO_BASE_URL, DISPLAY_CURRENCY
from services.cache import price_cache, historical_cache, rate_cache

logger = logging.getLogger(__name__)


class CoinGeckoClient:
    """Client for CoinGecko API (free, no API key required)."""

    def __init__(self):
        self.base_url = COINGECKO_BASE_URL
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "TradeRadar/1.0"
        })

    def get_prices(self, coin_ids: list[str], vs_currency: str = DISPLAY_CURRENCY) -> dict:
        """Batch get current prices for multiple coins (caches individual results)."""
        results = {}
        missing_ids = []

        for cid in coin_ids:
            cache_key = f"price:{cid}:{vs_currency}"
            cached = price_cache.get(cache_key)
            if cached is not None:
                results[cid] = cached
            else:
                missing_ids.append(cid)

        if not missing_ids:
            return results

        try:
            url = f"{self.base_url}/simple/price"
            params = {
                "ids": ",".join(missing_ids),
                "vs_currencies": vs_currency,
                "include_24hr_vol": "true",
                "include_24hr_change": "true",
                "include_market_cap": "true",
                "include_last_updated_at": "true"
            }
            resp = self.session.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            for cid in missing_ids:
                if cid in data:
                    coin_data = data[cid]
                    res = {
                        "price": coin_data.get(vs_currency, 0),
                        "volume_24h": coin_data.get(f"{vs_currency}_24h_vol", 0),
                        "change_24h": coin_data.get(f"{vs_currency}_24h_change", 0),
                        "market_cap": coin_data.get(f"{vs_currency}_market_cap", 0),
                    }
                    price_cache.set(f"price:{cid}:{vs_currency}", res)
                    results[cid] = res
                else:
                    results[cid] = None
        except Exception as e:
            logger.error(f"CoinGecko batch price error for {missing_ids}: {e}")
            for cid in missing_ids:
                results[cid] = None

        return results

    def get_price(self, coin_id: str, vs_currency: str = DISPLAY_CURRENCY) -> Optional[dict]:
        """Get current price for a coin (cached 2 min)."""
        return self.get_prices([coin_id], vs_currency).get(coin_id)


    def get_market_chart(self, coin_id: str, days: int = 30, vs_currency: str = DISPLAY_CURRENCY) -> Optional[dict]:
        """Get historical price data (cached 30 min)."""
        cache_key = f"chart:{coin_id}:{days}:{vs_currency}"
        cached = historical_cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            url = f"{self.base_url}/coins/{coin_id}/market_chart"
            params = {
                "vs_currency": vs_currency,
                "days": str(days),
                "interval": "daily" if days > 1 else "hourly"
            }
            resp = self.session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            prices = data.get("prices", [])
            volumes = data.get("total_volumes", [])
            market_caps = data.get("market_caps", [])

            result = {
                "prices": [{"timestamp": p[0], "price": p[1]} for p in prices],
                "volumes": [{"timestamp": v[0], "volume": v[1]} for v in volumes],
                "market_caps": [{"timestamp": m[0], "market_cap": m[1]} for m in market_caps],
            }
            historical_cache.set(cache_key, result)
            return result
        except Exception as e:
            logger.error(f"CoinGecko market chart error for {coin_id}: {e}")
            return None

    def get_ohlc(self, coin_id: str, days: int = 30, vs_currency: str = DISPLAY_CURRENCY) -> Optional[list]:
        """Get OHLC candlestick data (cached 30 min)."""
        cache_key = f"ohlc:{coin_id}:{days}:{vs_currency}"
        cached = historical_cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            url = f"{self.base_url}/coins/{coin_id}/ohlc"
            params = {"vs_currency": vs_currency, "days": str(days)}
            resp = self.session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            result = [
                {"timestamp": d[0], "open": d[1], "high": d[2], "low": d[3], "close": d[4]}
                for d in data
            ]
            historical_cache.set(cache_key, result)
            return result
        except Exception as e:
            logger.error(f"CoinGecko OHLC error for {coin_id}: {e}")
            return None

    def search_coin(self, query: str) -> Optional[list]:
        """Search for a coin by name or symbol."""
        try:
            url = f"{self.base_url}/search"
            params = {"query": query}
            resp = self.session.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            coins = data.get("coins", [])
            return [
                {
                    "id": c["id"],
                    "symbol": c["symbol"],
                    "name": c["name"],
                    "market_cap_rank": c.get("market_cap_rank"),
                }
                for c in coins[:10]
            ]
        except Exception as e:
            logger.error(f"CoinGecko search error: {e}")
            return None

    def ping(self) -> bool:
        """Check if CoinGecko API is reachable."""
        try:
            resp = self.session.get(f"{self.base_url}/ping", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def get_usd_eur_rate(self) -> float:
        """Get current USD to EUR exchange rate (cached 5 min)."""
        cache_key = "usd_eur_rate"
        cached = rate_cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            url = f"{self.base_url}/simple/price"
            params = {
                "ids": "bitcoin",
                "vs_currencies": "usd,eur"
            }
            resp = self.session.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            btc = data.get("bitcoin", {})
            usd_price = btc.get("usd", 1)
            eur_price = btc.get("eur", 1)
            if usd_price > 0:
                rate = eur_price / usd_price
                logger.info(f"USD/EUR rate: {rate:.4f}")
                rate_cache.set(cache_key, rate)
                return rate
            return 0.92  # fallback
        except Exception as e:
            logger.error(f"Error fetching USD/EUR rate: {e}")
            return 0.92  # fallback approximate rate
