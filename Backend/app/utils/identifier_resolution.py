"""
Multi-tiered identifier resolution (SKU or ID).
"""
from typing import Optional
import logging
from app.utils.local_sku_resolver import get_local_resolver

logger = logging.getLogger(__name__)


async def resolve_sku_or_id(identifier: str, bom_service) -> Optional[str]:
    """
    Resolve SKU or ID to internal ID.
    1. Try in-memory cache (fast)
    2. Try PostgreSQL (fast)
    3. Try NetSuite (slow), then save to DB
    """
    local_resolver = get_local_resolver()

    # 1. Try in-memory cache
    local_id = local_resolver.get_id_by_sku(identifier)
    if local_id:
        logger.info(f"Resolved {identifier} -> {local_id} from cache")
        return local_id

    # 2. Try DB lookup on cache miss
    db_id = await local_resolver.db_lookup_by_sku(identifier)
    if db_id:
        logger.info(f"Resolved {identifier} -> {db_id} from database")
        return db_id

    # 3. If numeric ID, check cache/DB/NetSuite
    if identifier.isdigit():
        if local_resolver.get_sku_by_id(identifier):
            logger.info(f"{identifier} is already a valid internal ID (cache)")
            return identifier
        db_sku = await local_resolver.db_lookup_by_id(identifier)
        if db_sku:
            logger.info(f"{identifier} is a valid internal ID (database)")
            return identifier
        item = await bom_service.get_item_details(identifier)
        if item:
            logger.info(f"{identifier} is a valid internal ID (NetSuite verified)")
            # Save to DB for future lookups
            item_sku = item.get("itemid", identifier)
            item_name = item.get("displayname") or item.get("description", "")
            await local_resolver.save_item(identifier, item_sku, item_name)
            return identifier

    # 4. Fallback to NetSuite SKU lookup
    logger.warning(f"Identifier {identifier} not found locally, querying NetSuite")
    netsuite_id = await bom_service.get_item_id_by_sku(identifier)

    if netsuite_id:
        logger.info(f"Resolved {identifier} -> {netsuite_id} from NetSuite")
        # Fetch item details to get description before saving
        item_name = None
        try:
            item_details = await bom_service.get_item_details(netsuite_id)
            if item_details:
                item_name = item_details.get("description") or item_details.get("displayname") or ""
        except Exception as e:
            logger.warning(f"Could not fetch details for {netsuite_id}: {e}")
        await local_resolver.save_item(netsuite_id, identifier, item_name)

    return netsuite_id
