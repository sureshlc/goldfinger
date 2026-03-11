"""
Local SKU Resolver - In-memory L1 cache backed by PostgreSQL.
"""
import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)


class LocalSKUResolver:
    def __init__(self):
        self.sku_to_id: Dict[str, str] = {}
        self.id_to_sku: Dict[str, str] = {}

    async def load_from_db(self):
        """Load items from PostgreSQL into memory cache."""
        try:
            from app.database.connection import get_session_factory
            from sqlalchemy import select
            from app.database.models import ItemDB

            factory = get_session_factory()
            async with factory() as session:
                result = await session.execute(select(ItemDB))
                items = result.scalars().all()
                count = 0
                for item in items:
                    item_id = str(item.id).strip()
                    item_sku = str(item.sku).strip()
                    if item_id and item_sku:
                        self.sku_to_id[item_sku] = item_id
                        self.id_to_sku[item_id] = item_sku
                        count += 1
                logger.info(f"Loaded {count} items from database into cache")
        except Exception as e:
            logger.error(f"Failed to load items from database: {e}")

    def get_id_by_sku(self, sku: str) -> Optional[str]:
        """Fast O(1) lookup of ID by SKU."""
        normalized_sku = str(sku).strip()
        return self.sku_to_id.get(normalized_sku)

    def get_sku_by_id(self, item_id: str) -> Optional[str]:
        """Fast O(1) lookup of SKU by ID."""
        return self.id_to_sku.get(str(item_id).strip())

    async def db_lookup_by_sku(self, sku: str) -> Optional[str]:
        """On cache miss, check PostgreSQL."""
        try:
            from app.database.connection import get_session_factory
            from app.database.repositories.item_repo import get_item_by_sku

            factory = get_session_factory()
            async with factory() as session:
                item = await get_item_by_sku(session, sku)
                if item:
                    self.sku_to_id[str(item.sku)] = str(item.id)
                    self.id_to_sku[str(item.id)] = str(item.sku)
                    return str(item.id)
        except Exception as e:
            logger.error(f"DB lookup failed for SKU {sku}: {e}")
        return None

    async def db_lookup_by_id(self, item_id: str) -> Optional[str]:
        """On cache miss, check PostgreSQL."""
        try:
            from app.database.connection import get_session_factory
            from app.database.repositories.item_repo import get_item_by_id

            factory = get_session_factory()
            async with factory() as session:
                item = await get_item_by_id(session, int(item_id))
                if item:
                    self.sku_to_id[str(item.sku)] = str(item.id)
                    self.id_to_sku[str(item.id)] = str(item.sku)
                    return str(item.sku)
        except Exception as e:
            logger.error(f"DB lookup failed for ID {item_id}: {e}")
        return None

    async def save_item(self, item_id: str, sku: str, name: str = None):
        """Upsert item to DB and update in-memory cache."""
        try:
            from app.database.connection import get_session_factory
            from app.database.repositories.item_repo import upsert_item

            factory = get_session_factory()
            async with factory() as session:
                await upsert_item(session, int(item_id), sku, name)
                await session.commit()

            self.sku_to_id[str(sku).strip()] = str(item_id).strip()
            self.id_to_sku[str(item_id).strip()] = str(sku).strip()
            logger.info(f"Saved item {item_id} ({sku}) to DB and cache")
        except Exception as e:
            logger.error(f"Failed to save item to DB: {e}")

    async def reload(self):
        """Reload cache from database."""
        self.sku_to_id.clear()
        self.id_to_sku.clear()
        await self.load_from_db()


# Singleton instance
_resolver_instance = None


def get_local_resolver() -> LocalSKUResolver:
    """Get the singleton local resolver instance."""
    global _resolver_instance
    if _resolver_instance is None:
        _resolver_instance = LocalSKUResolver()
    return _resolver_instance
