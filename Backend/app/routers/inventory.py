from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional
from pydantic import BaseModel
from app.services.inventory_service import InventoryService
from app.services.bom_service import BOMService
from app.services.service_registry import get_bom_service, get_inventory_service
from app.utils.identifier_resolution import resolve_sku_or_id
from app.utils.suiteql_sanitizer import validate_suiteql_identifier
from app.dependencies.auth import get_current_user
from app.models.user import User
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

class InventoryLevel(BaseModel):
    item_id: str
    item_name: str
    item_sku: str
    available_quantity: float
    inventory_status: Optional[str] = None
    location_name: Optional[str] = None

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
            inventory_status=item.get("inventory_status"),
            location_name=item.get("location_name")
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting item inventory: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get item inventory")
