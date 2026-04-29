"""
Multi-tiered identifier resolution (SKU or ID).
"""
from typing import Optional
import logging
from app.utils.local_sku_resolver import get_local_resolver

logger = logging.getLogger(__name__)


async def _verify_local_match(identifier: str, item_id: str, bom_service) -> bool:
    """
    Confirm that the locally-resolved internal id still maps to the user's SKU
    in NetSuite. If NetSuite reports a different itemid, the local row is stale —
    update it so the in-memory + DB caches reflect reality, and signal the caller
    to fall through to a fresh NetSuite SKU lookup.
    """
    if identifier.isdigit():
        return True

    details = await bom_service.get_item_details(item_id)
    if not details:
        return True

    netsuite_sku = (details.get("itemid") or "").strip()
    if not netsuite_sku or netsuite_sku.upper() == identifier.upper():
        return True

    logger.warning(
        f"Stale local mapping: identifier={identifier} -> id={item_id} but NetSuite "
        f"reports itemid={netsuite_sku}. Healing local cache."
    )
    name = details.get("description") or details.get("displayname") or ""
    await get_local_resolver().save_item(item_id, netsuite_sku, name)
    return False


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
        if await _verify_local_match(identifier, local_id, bom_service):
            logger.info(f"Resolved {identifier} -> {local_id} from cache")
            return local_id

    # 2. Try DB lookup on cache miss
    db_id = await local_resolver.db_lookup_by_sku(identifier)
    if db_id:
        if await _verify_local_match(identifier, db_id, bom_service):
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
