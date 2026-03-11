"""
Cache Manager with TTL support for BOM, Item Details, and Inventory
Designed to integrate with existing production_service.py

Caching Strategy:
- BOM structures: CACHED (1 hour default)
- Item details: CACHED (1 hour default)
- Inventory levels: CACHED (5 minutes default) - short TTL for near-real-time accuracy
"""
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class CacheManager:
    """
    Manages caching for BOM, item details, and inventory data.

    Usage:
        cache = CacheManager(bom_ttl_seconds=3600, item_details_ttl_seconds=3600, inventory_ttl_seconds=300)

        # Set a value
        cache.set("bom:SKU-123", bom_data)
        cache.set("inventory:123,456", inventory_data)

        # Get a value
        data = cache.get("bom:SKU-123")  # Returns None if expired or not found

        # Invalidate specific key
        cache.invalidate("bom:SKU-123")

        # Invalidate by pattern
        cache.invalidate_pattern("bom:")  # Clear all BOMs
        cache.invalidate_pattern("inventory:")  # Clear all inventory

        # Get statistics
        stats = cache.get_stats()
        cache.print_stats()
    """

    def __init__(self, bom_ttl_seconds: int = 3600, item_details_ttl_seconds: int = 3600, inventory_ttl_seconds: int = 300):
        """
        Initialize cache manager with different TTLs for different data types.

        Args:
            bom_ttl_seconds: TTL for BOM data (default: 1 hour)
            item_details_ttl_seconds: TTL for item details (default: 1 hour)
            inventory_ttl_seconds: TTL for inventory data (default: 5 minutes)
        """
        self._cache: Dict[str, Dict[str, Any]] = {}
        self.bom_ttl = bom_ttl_seconds
        self.item_details_ttl = item_details_ttl_seconds
        self.inventory_ttl = inventory_ttl_seconds

        # Statistics for monitoring
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
        """Get appropriate TTL based on cache key prefix"""
        if key.startswith('bom:'):
            return self.bom_ttl
        elif key.startswith('item_details:') or key.startswith('resolution:'):
            return self.item_details_ttl
        elif key.startswith('inventory:'):
            return self.inventory_ttl
        return 3600  # Default 1 hour

    def _get_stats_category(self, key: str) -> str:
        """Get stats category from cache key"""
        if key.startswith('bom:'):
            return 'bom'
        elif key.startswith('item_details:'):
            return 'item_details'
        elif key.startswith('resolution:'):
            return 'resolution'
        elif key.startswith('inventory:'):
            return 'inventory'
        return 'other'
    
    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache if not expired.
        
        Args:
            key: Cache key (e.g., "bom:SKU-123", "item_details:12345")
            
        Returns:
            Cached value if exists and not expired, None otherwise
        """
        category = self._get_stats_category(key)
        
        if key in self._cache:
            cache_data = self._cache[key]
            ttl = self._get_ttl_for_prefix(key)
            age = datetime.now() - cache_data['timestamp']
            
            if age < timedelta(seconds=ttl):
                self.stats[category]['hits'] += 1
                logger.debug(f"Cache HIT for key: {key} (age: {age.seconds}s)")
                return cache_data['value']
            else:
                # Expired
                self.stats[category]['expirations'] += 1
                del self._cache[key]
                logger.debug(f"Cache EXPIRED for key: {key} (age: {age.seconds}s)")
        
        self.stats[category]['misses'] += 1
        logger.debug(f"Cache MISS for key: {key}")
        return None
    
    def set(self, key: str, value: Any) -> None:
        """
        Set value in cache with current timestamp.
        
        Args:
            key: Cache key (e.g., "bom:SKU-123", "item_details:12345")
            value: Value to cache (can be dict, list, string, etc.)
        """
        self._cache[key] = {
            'value': value,
            'timestamp': datetime.now()
        }
        logger.debug(f"Cached value for key: {key}")
    
    def invalidate(self, key: str) -> None:
        """
        Remove specific key from cache.
        
        Args:
            key: Cache key to invalidate
        """
        if key in self._cache:
            del self._cache[key]
            logger.info(f"Invalidated cache for key: {key}")
    
    def invalidate_pattern(self, pattern: str) -> int:
        """
        Invalidate all keys matching a pattern.
        
        Args:
            pattern: Pattern to match (e.g., 'bom:' to clear all BOMs)
            
        Returns:
            Number of keys invalidated
            
        Example:
            cache.invalidate_pattern('bom:')  # Clear all BOMs
            cache.invalidate_pattern('item_details:')  # Clear all item details
            cache.invalidate_pattern('SKU-123')  # Clear anything related to SKU-123
        """
        keys_to_delete = [k for k in self._cache.keys() if pattern in k]
        for key in keys_to_delete:
            del self._cache[key]
        
        if keys_to_delete:
            logger.info(f"Invalidated {len(keys_to_delete)} cache entries matching '{pattern}'")
        
        return len(keys_to_delete)
    
    def clear(self) -> None:
        """Clear entire cache"""
        count = len(self._cache)
        self._cache.clear()
        
        # Reset stats
        for category in self.stats:
            self.stats[category] = {'hits': 0, 'misses': 0, 'expirations': 0}
        
        logger.info(f"Cache cleared ({count} entries removed)")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with hit rates and counts for each category
            
        Example:
            stats = cache.get_stats()
            print(f"BOM hit rate: {stats['bom']['hit_rate']}")
            print(f"Cache size: {stats['cache_size']}")
        """
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
    
    def print_stats(self) -> None:
        """
        Print cache statistics in a readable format.
        
        Example output:
            ============================================================
            CACHE STATISTICS
            ============================================================
            
            BOM:
              Hits: 45
              Misses: 10
              Expirations: 2
              Hit Rate: 81.82%
            
            ITEM DETAILS:
              Hits: 38
              Misses: 12
              Expirations: 1
              Hit Rate: 76.00%
            
            RESOLUTION:
              Hits: 50
              Misses: 5
              Expirations: 0
              Hit Rate: 90.91%
            
            Total Cached Items: 87
            ============================================================
        """
        stats = self.get_stats()
        
        print("\n" + "="*60)
        print("CACHE STATISTICS")
        print("="*60)
        
        for category, data in stats.items():
            if category != 'cache_size':
                print(f"\n{category.upper().replace('_', ' ')}:")
                print(f"  Hits: {data['hits']}")
                print(f"  Misses: {data['misses']}")
                print(f"  Expirations: {data['expirations']}")
                print(f"  Hit Rate: {data['hit_rate']}")
        
        print(f"\nTotal Cached Items: {stats['cache_size']}")
        print("="*60 + "\n")
    
    def get_cache_size_bytes(self) -> int:
        """
        Estimate cache size in bytes (approximate).
        
        Returns:
            Approximate cache size in bytes
        """
        import sys
        total_size = 0
        for key, value in self._cache.items():
            total_size += sys.getsizeof(key)
            total_size += sys.getsizeof(value)
        return total_size
    
    def get_all_keys(self) -> list:
        """
        Get all cache keys (useful for debugging).
        
        Returns:
            List of all cache keys
        """
        return list(self._cache.keys())


# Utility functions for cache key generation
def make_bom_cache_key(item_sku: str) -> str:
    """
    Generate cache key for BOM data.
    
    Args:
        item_sku: Item SKU (e.g., "WIDGET-A")
        
    Returns:
        Cache key string (e.g., "bom:WIDGET-A")
    """
    return f"bom:{item_sku}"


def make_item_details_cache_key(item_id: str) -> str:
    """
    Generate cache key for item details.
    
    Args:
        item_id: Item internal ID (e.g., "12345")
        
    Returns:
        Cache key string (e.g., "item_details:12345")
    """
    return f"item_details:{item_id}"


def make_resolution_cache_key(identifier: str) -> str:
    """
    Generate cache key for SKU/ID resolution.

    Args:
        identifier: SKU or ID to resolve (e.g., "SKU-123" or "12345")

    Returns:
        Cache key string (e.g., "resolution:SKU-123")
    """
    return f"resolution:{identifier}"


def make_inventory_cache_key(item_ids: list, location_name: str = None) -> str:
    """
    Generate cache key for inventory data.

    Args:
        item_ids: List of item IDs
        location_name: Optional location filter

    Returns:
        Cache key string (e.g., "inventory:123,456|loc:Main")
    """
    sorted_ids = ",".join(sorted(str(i) for i in item_ids))
    loc = f"|loc:{location_name}" if location_name else ""
    return f"inventory:{sorted_ids}{loc}"


# Example usage (for documentation)
if __name__ == "__main__":
    # Initialize cache
    cache = CacheManager(bom_ttl_seconds=3600, item_details_ttl_seconds=3600)
    
    # Store some data
    cache.set(make_bom_cache_key("WIDGET-A"), {"components": ["PART-1", "PART-2"]})
    cache.set(make_item_details_cache_key("12345"), {"name": "Widget A", "type": "Assembly"})
    cache.set(make_resolution_cache_key("SKU-123"), "12345")
    
    # Retrieve data
    bom = cache.get(make_bom_cache_key("WIDGET-A"))
    print(f"BOM: {bom}")
    
    # Check stats
    cache.print_stats()
    
    # Invalidate specific item
    cache.invalidate(make_bom_cache_key("WIDGET-A"))
    
    # Clear all BOMs
    count = cache.invalidate_pattern("bom:")
    print(f"Cleared {count} BOM entries")
    
    # Clear everything
    cache.clear()