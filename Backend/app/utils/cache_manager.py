"""
Cache Manager with TTL support and asyncio.Lock for thread safety.

Caching Strategy:
- BOM structures: CACHED (1 hour default)
- Item details: CACHED (1 hour default)
- Inventory levels: CACHED (5 minutes default) - short TTL for near-real-time accuracy
"""
import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class CacheManager:
    """
    Thread-safe async cache manager for BOM, item details, and inventory data.
    All dict operations are protected by asyncio.Lock.
    """

    def __init__(self, bom_ttl_seconds: int = 3600, item_details_ttl_seconds: int = 3600, inventory_ttl_seconds: int = 300):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self.bom_ttl = bom_ttl_seconds
        self.item_details_ttl = item_details_ttl_seconds
        self.inventory_ttl = inventory_ttl_seconds

        self.stats = {
            'bom': {'hits': 0, 'misses': 0, 'expirations': 0},
            'item_details': {'hits': 0, 'misses': 0, 'expirations': 0},
            'resolution': {'hits': 0, 'misses': 0, 'expirations': 0},
            'inventory': {'hits': 0, 'misses': 0, 'expirations': 0}
        }

        logger.info(
            f"CacheManager initialized: BOM TTL={bom_ttl_seconds}s, "
            f"Item Details TTL={item_details_ttl_seconds}s, "
            f"Inventory TTL={inventory_ttl_seconds}s"
        )

    def _get_ttl_for_prefix(self, key: str) -> int:
        if key.startswith('bom:'):
            return self.bom_ttl
        elif key.startswith('item_details:') or key.startswith('resolution:'):
            return self.item_details_ttl
        elif key.startswith('inventory:'):
            return self.inventory_ttl
        return 3600

    def _get_stats_category(self, key: str) -> str:
        if key.startswith('bom:'):
            return 'bom'
        elif key.startswith('item_details:'):
            return 'item_details'
        elif key.startswith('resolution:'):
            return 'resolution'
        elif key.startswith('inventory:'):
            return 'inventory'
        return 'other'

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired (thread-safe)."""
        category = self._get_stats_category(key)

        async with self._lock:
            if key in self._cache:
                cache_data = self._cache[key]
                ttl = self._get_ttl_for_prefix(key)
                age = datetime.now() - cache_data['timestamp']

                if age < timedelta(seconds=ttl):
                    self.stats[category]['hits'] += 1
                    logger.debug(f"Cache HIT for key: {key} (age: {age.seconds}s)")
                    return cache_data['value']
                else:
                    self.stats[category]['expirations'] += 1
                    del self._cache[key]
                    logger.debug(f"Cache EXPIRED for key: {key} (age: {age.seconds}s)")

            self.stats[category]['misses'] += 1
            logger.debug(f"Cache MISS for key: {key}")
            return None

    async def set(self, key: str, value: Any) -> None:
        """Set value in cache (thread-safe)."""
        async with self._lock:
            self._cache[key] = {
                'value': value,
                'timestamp': datetime.now()
            }
        logger.debug(f"Cached value for key: {key}")

    async def invalidate(self, key: str) -> None:
        """Remove specific key from cache (thread-safe)."""
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                logger.info(f"Invalidated cache for key: {key}")

    async def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate all keys matching a pattern (thread-safe)."""
        async with self._lock:
            keys_to_delete = [k for k in self._cache.keys() if pattern in k]
            for key in keys_to_delete:
                del self._cache[key]

        if keys_to_delete:
            logger.info(f"Invalidated {len(keys_to_delete)} cache entries matching '{pattern}'")
        return len(keys_to_delete)

    async def clear(self) -> None:
        """Clear entire cache (thread-safe)."""
        async with self._lock:
            count = len(self._cache)
            self._cache.clear()
            for category in self.stats:
                self.stats[category] = {'hits': 0, 'misses': 0, 'expirations': 0}
        logger.info(f"Cache cleared ({count} entries removed)")

    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics (thread-safe)."""
        async with self._lock:
            stats_summary = {}
            for category, counts in self.stats.items():
                total_requests = counts['hits'] + counts['misses']
                hit_rate = counts['hits'] / total_requests if total_requests > 0 else 0.0
                stats_summary[category] = {
                    'hits': counts['hits'],
                    'misses': counts['misses'],
                    'expirations': counts['expirations'],
                    'total_requests': total_requests,
                    'hit_rate': f"{hit_rate:.2%}",
                    'hit_rate_decimal': hit_rate
                }
            stats_summary['cache_size'] = len(self._cache)
            return stats_summary


# Utility functions for cache key generation
def make_bom_cache_key(item_sku: str) -> str:
    return f"bom:{item_sku}"


def make_item_details_cache_key(item_id: str) -> str:
    return f"item_details:{item_id}"


def make_resolution_cache_key(identifier: str) -> str:
    return f"resolution:{identifier}"


def make_inventory_cache_key(item_ids: list, location_name: str = None) -> str:
    sorted_ids = ",".join(sorted(str(i) for i in item_ids))
    loc = f"|loc:{location_name}" if location_name else ""
    return f"inventory:{sorted_ids}{loc}"
