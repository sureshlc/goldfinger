from typing import List, Dict, Optional
from app.services.netsuite_service import NetSuiteService
from app.utils.suiteql_sanitizer import validate_numeric_id, validate_suiteql_identifier, sanitize_suiteql_value, validate_numeric_value
import logging
import time

logger = logging.getLogger(__name__)

class InventoryService:
    def __init__(self, netsuite_service: NetSuiteService):
        self.netsuite_service = netsuite_service

    async def get_inventory_levels(self, item_ids: List[str], location_name: Optional[str] = None) -> List[Dict]:
        """
        Get inventory levels for multiple items filtered optionally by location.
        """
        start_time = time.time()

        for item_id in item_ids:
            validate_numeric_id(item_id, "item_id")
        item_list = "', '".join(item_ids)

        location_filter = ""
        if location_name:
            validate_suiteql_identifier(location_name, "location_name")
            safe_location = sanitize_suiteql_value(location_name)
            location_filter = f"AND BUILTIN.DF(ib.location) = '{safe_location}'"

        sql = f"""
        WITH CTE AS (
        SELECT 
            ib.item as item_id,
            i.itemid as item_sku,
            i.displayname as item_name,
            sum(ib.quantityavailable) as quantity_available,
            ib.committedqtyperlocation as committed_quantity,
            BUILTIN.DF(inventorystatus) as inventory_status,
            BUILTIN.DF(ib.location) as location_name
        FROM inventorybalance ib
        JOIN item i ON ib.item = i.id
        WHERE BUILTIN.DF(inventorystatus)='Good'
        AND ib.item IN ('{item_list}')
        {location_filter}
        GROUP BY ib.item, i.itemid, i.displayname, BUILTIN.DF(inventorystatus), BUILTIN.DF(ib.location), ib.committedqtyperlocation
        ORDER BY i.itemid ASC)

        SELECT 
            item_id, 
            item_sku, 
            item_name, 
            CASE 
                WHEN sum(quantity_available - committed_quantity) < 0 THEN 0
                ELSE sum(quantity_available - committed_quantity)
            END AS available_quantity, 
            inventory_status
        FROM CTE
        GROUP BY item_id, item_sku, item_name, inventory_status
        """

        try:
            result = await self.netsuite_service.execute_suiteql(sql)
            
            elapsed = time.time() - start_time
            logger.info(f"[TIMING] get_inventory_levels for {len(item_ids)} items took {elapsed:.3f}s")
            
            return result.get('items', [])
        except Exception as e:
            logger.error(f"Failed to get inventory levels for items {item_ids}: {e}")
            return []

    async def get_low_stock_items(self, threshold: float = 10.0, location_name: Optional[str] = None) -> List[Dict]:
        """
        Get list of items with available quantity less than or equal to threshold.
        """
        start_time = time.time()

        safe_threshold = validate_numeric_value(threshold, "threshold")

        location_filter = ""
        if location_name:
            validate_suiteql_identifier(location_name, "location_name")
            safe_location = sanitize_suiteql_value(location_name)
            location_filter = f"AND BUILTIN.DF(ib.location) = '{safe_location}'"

        sql = f"""
        SELECT
            ib.item as item_id,
            i.itemid as item_sku,
            i.displayname as item_name,
            ib.quantityavailable as available_quantity,
            BUILTIN.DF(inventorystatus) as inventory_status,
            BUILTIN.DF(ib.location) as location_name
        FROM inventorybalance ib
        JOIN item i ON ib.item = i.id
        WHERE ib.quantityavailable <= {safe_threshold}
        {location_filter}
        ORDER BY ib.quantityavailable ASC
        """

        try:
            result = await self.netsuite_service.execute_suiteql(sql)
            
            elapsed = time.time() - start_time
            logger.info(f"[TIMING] get_low_stock_items took {elapsed:.3f}s")
            
            return result.get('items', [])
        except Exception as e:
            logger.error(f"Failed to get low stock items: {e}")
            return []