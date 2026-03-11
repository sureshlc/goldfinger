import csv
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from pydantic import BaseModel
from app.services.bom_service import BOMService
from app.services.netsuite_service import NetSuiteService
from app.utils.identifier_resolution import resolve_sku_or_id
from app.utils.suiteql_sanitizer import validate_suiteql_identifier
import logging
from app.dependencies.auth import get_current_user
from app.models.user import User


router = APIRouter()
logger = logging.getLogger(__name__)


class ItemDetailsResponse(BaseModel):
    id: str
    name: str
    sku: str
    item_type: str
    description: Optional[str] = ""
    is_manufacturing: bool


class BOMComponent(BaseModel):
    item_id: str
    item_name: str
    item_sku: str
    quantity_required: float
    unit: str
    level: int  # nesting level to indicate multi-level BOM depth


class BOMResponse(BaseModel):
    parent_item_sku: str
    components: List[BOMComponent]
    total_components: int


async def get_bom_service():
    netsuite_service = NetSuiteService()
    return BOMService(netsuite_service)


@router.get("/sku/{item_sku}", response_model=ItemDetailsResponse, summary="Get detailed item information by SKU")
async def get_item_details_by_sku(
    item_sku: str,
    current_user: User = Depends(get_current_user),
    bom_service: BOMService = Depends(get_bom_service)
):
    try:
        validate_suiteql_identifier(item_sku, "item_sku")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    logger.info(f"Getting item details for SKU: {item_sku}")
    item_id = await resolve_sku_or_id(item_sku, bom_service)
    logger.debug(f"Resolved SKU {item_sku} to ID: {item_id}")
    
    if not item_id:
        raise HTTPException(status_code=404, detail="Item not found for SKU")
    
    item = await bom_service.get_item_details(item_id)
    logger.debug(f"NetSuite returned item details: {item}")
    
    if not item:
        raise HTTPException(status_code=404, detail="Item details not found in NetSuite")
    return ItemDetailsResponse(
        id=item["id"],
        name=item["displayname"],
        sku=item["itemid"],
        item_type=item["itemtype"],
        description=item.get("description", ""),
        is_manufacturing=item["is_manufacturing"] == "true"
    )


@router.get("/sku/{item_sku}/bom", response_model=BOMResponse, summary="Get multi-level Bill of Materials for an item by SKU")
async def get_item_bom_by_sku(
    item_sku: str,
    current_user: User = Depends(get_current_user),
    bom_service: BOMService = Depends(get_bom_service)
):
    try:
        validate_suiteql_identifier(item_sku, "item_sku")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    logger.info(f"Getting multi-level BOM for item SKU: {item_sku}")
    item_id = await resolve_sku_or_id(item_sku, bom_service)
    if not item_id:
        raise HTTPException(status_code=404, detail="BOM not found for this SKU")
    bom_components = await bom_service.get_full_bom(item_sku)
    formatted_components = []
    for component in bom_components:
        formatted_components.append(BOMComponent(
            item_id=component["bom_id"],
            item_name=component.get("component_displayname") or component.get("component_name") or "",
            item_sku=component["component_sku"],
            quantity_required=float(component["quantity_required"]),
            unit=component.get("unit") or "N/A",
            level=component.get("level", 0)  # use level info to show nesting
        ))
    return BOMResponse(
        parent_item_sku=item_sku,
        components=formatted_components,
        total_components=len(formatted_components)
    )
