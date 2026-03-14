"""
TradeRadar - In-Memory TTL Cache
Simple thread-safe cache to reduce API calls and avoid rate limits.
"""
import time
import logging
import threading
from typing import Any, Optional

logger = logging.getLogger(__name__)


class TTLCache:
    """Thread-safe in-memory cache with per-key TTL."""

    def __init__(self, default_ttl: int = 120):
        """
        Args:
            default_ttl: Default time-to-live in seconds.
        """
        self.default_ttl = default_ttl
        self._store: dict[str, tuple[Any, float]] = {}  # key -> (value, expiry_timestamp)
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        """Get a value from cache. Returns None if expired or missing."""
        with self._lock:
            if key in self._store:
                value, expiry = self._store[key]
                if time.time() < expiry:
                    self._hits += 1
                    return value
                else:
                    # Expired, clean up
                    del self._store[key]
            self._misses += 1
            return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Store a value with optional custom TTL."""
        ttl = ttl if ttl is not None else self.default_ttl
        with self._lock:
            self._store[key] = (value, time.time() + ttl)

    def has(self, key: str) -> bool:
        """Check if key exists and is not expired."""
        return self.get(key) is not None

    def invalidate(self, key: str):
        """Remove a specific key."""
        with self._lock:
            self._store.pop(key, None)

    def clear(self):
        """Clear all cached entries."""
        with self._lock:
            self._store.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> dict:
        """Get cache statistics."""
        with self._lock:
            total = self._hits + self._misses
            return {
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": f"{(self._hits / total * 100):.1f}%" if total > 0 else "N/A",
                "size": len(self._store),
            }

    def cleanup(self):
        """Remove all expired entries."""
        now = time.time()
        with self._lock:
            expired = [k for k, (_, exp) in self._store.items() if now >= exp]
            for k in expired:
                del self._store[k]
            if expired:
                logger.debug(f"Cache cleanup: removed {len(expired)} expired entries")


# ─── Global cache instances ───────────────────────────────
# Prices: short TTL (2 min) — prices change frequently
price_cache = TTLCache(default_ttl=120)

# Historical data: long TTL (30 min) — doesn't change often
historical_cache = TTLCache(default_ttl=1800)

# Exchange rate: medium TTL (5 min) — changes slowly
rate_cache = TTLCache(default_ttl=300)
