"""
BOM Service with integrated caching support.
This version caches BOM fetches to avoid redundant NetSuite API calls.
"""
from typing import List, Dict, Optional
from app.services.netsuite_service import NetSuiteService
from app.utils.cache_manager import make_bom_cache_key, make_item_details_cache_key
from app.utils.suiteql_sanitizer import validate_suiteql_identifier, sanitize_suiteql_value, validate_numeric_id
import logging
import time

logger = logging.getLogger(__name__)


class BOMService:
    def __init__(self, netsuite_service: NetSuiteService, cache_manager=None):
        self.netsuite_service = netsuite_service
        self.cache_manager = cache_manager

        if cache_manager:
            logger.info("BOMService initialized WITH caching")
        else:
            logger.info("BOMService initialized WITHOUT caching")

    async def get_item_id_by_sku(self, item_sku: str) -> Optional[str]:
        start_time = time.time()

        validate_suiteql_identifier(item_sku, "item_sku")
        safe_sku = sanitize_suiteql_value(item_sku)

        sql = f"""
        SELECT id
        FROM item
        WHERE itemid = '{safe_sku}'
        AND isinactive = 'F'
        """
        try:
            logger.debug(f"[BOM] Executing query: {sql}")
            result = await self.netsuite_service.execute_suiteql(sql)
            items = result.get('items', [])

            logger.debug(f"[BOM] Query returned {len(items)} results")
            if items:
                logger.debug(f"[BOM] Found item ID: {items[0]['id']}")

            elapsed = time.time() - start_time
            logger.info(f"[TIMING] get_item_id_by_sku for {item_sku} took {elapsed:.3f}s")

            if items:
                return items[0]["id"]
            return None
        except Exception as e:
            logger.error(f"Failed to get internal ID for SKU {item_sku}: {e}")
            return None

    async def get_item_bom(self, item_id: str) -> List[Dict]:
        """Fetch Bill of Materials (BOM) components for a specific item ID."""
        start_time = time.time()
        validate_numeric_id(item_id, "item_id")

        sql = f"""
        SELECT
            b.id AS bom_id,
            b.name AS bom_name,
            item.id as internal_id,
            item.itemid as component_sku,
            (CASE WHEN item.displayname IS NULL THEN item.description ELSE item.displayname END) AS component_displayname,
            item.displayname,
            item.description AS component_name,
            ROUND(component.quantity, 5) as quantity_required,
            iu.name as unit,
            CASE WHEN item.itemtype IN ('Assembly', 'Kit') THEN 'true' ELSE 'false' END as is_manufacturing,
            CASE WHEN item.isphantom = 'T' THEN 'true' ELSE 'false' END as is_phantom
        FROM bomRevisionComponentMember AS component
        JOIN bomRevision AS rev ON component.bomRevision = rev.id
        JOIN bom as b ON rev.billofmaterials = b.id
        JOIN item ON component.item = item.id
        JOIN item parent_item ON b.custrecord_blend_bom_assembly = parent_item.id
        LEFT JOIN ItemUnit as iu ON component.units = iu.key
        WHERE parent_item.id = '{item_id}'
        AND item.id != 5837
        AND rev.isInactive = 'F'
        AND (rev.effectiveenddate IS NULL OR rev.effectiveenddate >= CURRENT_DATE)
        AND (rev.effectivestartdate IS NULL OR rev.effectivestartdate <= CURRENT_DATE)
        ORDER BY b.id
        """
        try:
            result = await self.netsuite_service.execute_suiteql(sql)
            items = result.get('items', [])

            elapsed = time.time() - start_time
            logger.info(f"[TIMING] get_item_bom for item {item_id} took {elapsed:.3f}s, returned {len(items)} components")

            return items
        except Exception as e:
            logger.error(f"Failed to fetch BOM for item {item_id}: {e}")
            return []

    async def get_item_details(self, item_id: str) -> Optional[Dict]:
        """Get detailed information for a specific item by ID. Uses cache if available."""
        # Check cache first
        if self.cache_manager:
            cache_key = make_item_details_cache_key(item_id)
            cached_details = await self.cache_manager.get(cache_key)
            if cached_details is not None:
                logger.debug(f"Cache HIT for item details: {item_id}")
                return cached_details

        start_time = time.time()
        validate_numeric_id(item_id, "item_id")

        sql = f"""
        SELECT
            id,
            itemid,
            COALESCE(description, itemid) as displayname,
            itemtype,
            description,
            CASE WHEN itemtype IN ('Assembly', 'Kit') THEN 'true' ELSE 'false' END as is_manufacturing
        FROM item
        WHERE id = '{item_id}'
        AND isinactive = 'F'
        """
        try:
            result = await self.netsuite_service.execute_suiteql(sql)
            items = result.get('items', [])

            elapsed = time.time() - start_time
            logger.info(f"[TIMING] get_item_details for {item_id} took {elapsed:.3f}s")

            item_details = items[0] if items else None

            # Cache the result
            if self.cache_manager and item_details:
                cache_key = make_item_details_cache_key(item_id)
                await self.cache_manager.set(cache_key, item_details)
                logger.debug(f"Cached item details for: {item_id}")

            return item_details
        except Exception as e:
            logger.error(f"Failed to get item details for item ID {item_id}: {e}")
            return None

    async def get_full_bom(self, item_sku: str, max_depth=5, current_depth=0) -> List[Dict]:
        """Recursively fetch the full multi-level BOM for an item by SKU, up to max_depth levels."""
        start_time = time.time()
        logger.info(f"[TIMING] get_full_bom called for SKU: {item_sku}, depth: {current_depth}")

        # Check cache at ALL depths
        if self.cache_manager:
            cache_key = make_bom_cache_key(item_sku)
            cached_bom = await self.cache_manager.get(cache_key)
            if cached_bom is not None:
                adjusted_bom = []
                for comp in cached_bom:
                    adjusted_comp = comp.copy()
                    adjusted_comp["level"] = comp.get("level", 0) + current_depth
                    adjusted_bom.append(adjusted_comp)

                elapsed = time.time() - start_time
                logger.info(f"[CACHE HIT] get_full_bom for {item_sku} at depth {current_depth} returned from cache in {elapsed:.3f}s, {len(adjusted_bom)} components")
                return adjusted_bom

        if current_depth > max_depth:
            return []

        item_id = await self.get_item_id_by_sku(item_sku)
        if not item_id:
            return []

        components = await self.get_item_bom(item_id)
        full_bom = []

        for component in components:
            component["level"] = current_depth
            full_bom.append(component)

            if component.get("is_manufacturing") == "true":
                sub_bom = await self.get_full_bom(
                    component["component_sku"],
                    max_depth,
                    current_depth + 1
                )
                full_bom.extend(sub_bom)

        elapsed = time.time() - start_time
        logger.info(f"[TIMING] get_full_bom for {item_sku} at depth {current_depth} took {elapsed:.3f}s, returned {len(full_bom)} total components")

        # Cache the result with base levels
        if self.cache_manager and full_bom:
            base_bom = []
            for comp in full_bom:
                base_comp = comp.copy()
                base_comp["level"] = comp.get("level", current_depth) - current_depth
                base_bom.append(base_comp)

            cache_key = make_bom_cache_key(item_sku)
            await self.cache_manager.set(cache_key, base_bom)
            logger.info(f"[CACHED] Full BOM for {item_sku} at depth {current_depth} cached with {len(base_bom)} components")

        return full_bom

    async def get_item_by_sku(self, item_sku: str) -> Optional[Dict]:
        """Get item details by SKU (used by production_service)."""
        item_id = await self.get_item_id_by_sku(item_sku)
        if not item_id:
            return None
        return await self.get_item_details(item_id)
