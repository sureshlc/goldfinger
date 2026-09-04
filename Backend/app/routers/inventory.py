from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional, List
from pydantic import BaseModel
from app.services.inventory_service import InventoryService
from app.services.bom_service import BOMService
from app.services.service_registry import get_bom_service, get_inventory_service
from app.utils.identifier_resolution import resolve_sku_or_id, resolve_skus_bulk
from app.utils.suiteql_sanitizer import validate_suiteql_identifier
from app.dependencies.auth import get_current_user
from app.models.user import User
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_BATCH_SKUS = 500
# Chunk the inventory query so no single SuiteQL nears NetSuite's 1000-row-per-page limit
# (our executor doesn't paginate). The query returns ~1 row per item, so 200 leaves wide
# headroom while keeping each call light. Decouples MAX_BATCH_SKUS from the NetSuite page cap.
INVENTORY_ID_CHUNK = 200

class InventoryLevel(BaseModel):
    item_id: str
    item_name: str
    item_sku: str
    available_quantity: float
    on_hand: Optional[float] = None
    committed: Optional[float] = None
    inventory_status: Optional[str] = None
    location_name: Optional[str] = None


class BatchInventoryRequest(BaseModel):
    skus: List[str]
    location_name: Optional[str] = None


class BatchInventoryItem(BaseModel):
    sku: str
    found: bool
    item_id: Optional[str] = None
    item_name: Optional[str] = None
    available_quantity: float = 0.0
    on_hand: Optional[float] = None
    committed: Optional[float] = None


class BatchInventoryResponse(BaseModel):
    items: List[BatchInventoryItem]
    count: int
    not_found: List[str] = []


@router.post("/batch", response_model=BatchInventoryResponse,
             summary="Get inventory for many SKUs in ONE batched call")
async def get_batch_inventory(
    request: BatchInventoryRequest,
    current_user: User = Depends(get_current_user),
    bom_service: BOMService = Depends(get_bom_service),
    inventory_service: InventoryService = Depends(get_inventory_service),
):
    """Batched inventory lookup for partner integrations (customer portal, MES).

    Resolves all SKUs to internal ids in ONE items-table query (NetSuite fallback only for the rare
    untabled SKU), then fetches all inventory in ONE SuiteQL (WHERE item IN (...)) via the same
    get_inventory_levels used everywhere — so availability is netted identically to the single
    endpoint (available = on_hand - committed, floored at 0). Unknown SKUs are reported in
    `not_found`; resolved SKUs with no stock return zeros.
    """
    # Dedup + strip, preserve order.
    skus = list(dict.fromkeys(s.strip() for s in request.skus if s and s.strip()))
    if not skus:
        return BatchInventoryResponse(items=[], count=0, not_found=[])
    if len(skus) > MAX_BATCH_SKUS:
        raise HTTPException(status_code=400, detail=f"Too many SKUs (max {MAX_BATCH_SKUS} per call)")
    try:
        for s in skus:
            validate_suiteql_identifier(s, "sku")
        if request.location_name:
            validate_suiteql_identifier(request.location_name, "location_name")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        # 1) One bulk SKU -> id resolution.
        resolved = await resolve_skus_bulk(skus, bom_service)

        # 2) Batched inventory query for all resolved ids, chunked so no single SuiteQL nears
        #    NetSuite's 1000-row page limit (our executor doesn't paginate).
        ids = [resolved[s]["id"] for s in skus if resolved.get(s, {}).get("id")]
        inv_rows = []
        for i in range(0, len(ids), INVENTORY_ID_CHUNK):
            chunk = ids[i:i + INVENTORY_ID_CHUNK]
            inv_rows.extend(await inventory_service.get_inventory_levels(chunk, request.location_name))
        inv_by_id = {str(r["item_id"]): r for r in inv_rows if "item_id" in r}

        items: List[BatchInventoryItem] = []
        not_found: List[str] = []
        for sku in skus:
            iid = resolved.get(sku, {}).get("id")
            if not iid:
                not_found.append(sku)
                items.append(BatchInventoryItem(sku=sku, found=False))
                continue
            row = inv_by_id.get(str(iid))
            if row:
                items.append(BatchInventoryItem(
                    sku=sku, found=True, item_id=str(iid),
                    item_name=row.get("item_name") or resolved[sku].get("name") or "",
                    available_quantity=float(row.get("available_quantity", 0) or 0),
                    on_hand=float(row.get("on_hand", 0) or 0),
                    committed=float(row.get("committed", 0) or 0),
                ))
            else:
                # Resolved but no inventory records -> zeros (same convention as the single endpoint).
                items.append(BatchInventoryItem(
                    sku=sku, found=True, item_id=str(iid),
                    item_name=resolved[sku].get("name") or "",
                    available_quantity=0.0, on_hand=0.0, committed=0.0,
                ))

        return BatchInventoryResponse(items=items, count=len(items), not_found=not_found)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting batch inventory: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get batch inventory")

@router.get("/{item_identifier}", response_model=InventoryLevel, summary="Get inventory for item by SKU or internal ID")
async def get_item_inventory(
    item_identifier: str,
    location_name: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    bom_service: BOMService = Depends(get_bom_service),
    inventory_service: InventoryService = Depends(get_inventory_service)
):
    """
    Get inventory info for a single item by SKU or internal ID.
    """
    try:
        validate_suiteql_identifier(item_identifier, "item_identifier")
        if location_name:
            validate_suiteql_identifier(location_name, "location_name")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        logger.info(f"Getting inventory for item ID or SKU: {item_identifier}")

        # Resolve the identifier
        resolved_id = await resolve_sku_or_id(item_identifier, bom_service)
        logger.info(f"Resolved {item_identifier} to ID: {resolved_id}")

        if not resolved_id:
            raise HTTPException(status_code=404, detail="Item not found")

        # Get item details to confirm it exists
        item_details = await bom_service.get_item_details(resolved_id)
        if not item_details:
            raise HTTPException(status_code=404, detail="Item not found")

        # Get inventory (may be empty if no inventory records)
        inventory_data = await inventory_service.get_inventory_levels([resolved_id], location_name)
        logger.debug(f"NetSuite returned inventory data: {inventory_data}")

        # Extract item name and SKU from item_details (always available)
        item_name = item_details.get("displayname", item_details.get("itemid", "Unknown"))
        item_sku = item_details.get("itemid", item_identifier)

        # Item exists but has no inventory - return zero inventory instead of 404
        if not inventory_data:
            logger.info(f"Item {resolved_id} exists but has no inventory records")
            return InventoryLevel(
                item_id=resolved_id,
                item_name=item_name,
                item_sku=item_sku,
                available_quantity=0.0,
                on_hand=0.0,
                committed=0.0,
                inventory_status="No inventory",
                location_name=location_name
            )

        # Return actual inventory data
        item = inventory_data[0]
        return InventoryLevel(
            item_id=item["item_id"],
            item_name=item_name,
            item_sku=item_sku,
            available_quantity=float(item.get("available_quantity", 0)),
            on_hand=float(item.get("on_hand", 0)),
            committed=float(item.get("committed", 0)),
            inventory_status=item.get("inventory_status"),
            location_name=item.get("location_name")
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting item inventory: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get item inventory")
