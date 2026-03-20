from fastapi import APIRouter, HTTPException, Query, Depends, Request
from typing import Optional, List
import logging
import time
from pydantic import BaseModel, ConfigDict, Field
from app.services.production_service import ProductionService
from app.services.service_registry import get_production_service, get_bom_service
from app.utils.suiteql_sanitizer import validate_suiteql_identifier
from app.dependencies.auth import get_current_user, get_admin_user
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()


class BOMComponent(BaseModel):
    item_id: str
    item_name: str
    item_sku: str
    quantity_required: float
    unit: str
    level: int

    model_config = ConfigDict(from_attributes=True)


class ProductionAnalysisResponse(BaseModel):
    item_id: str
    item_name: str
    item_sku: str
    can_produce: bool
    max_quantity_producible: int
    limiting_component: Optional[str]
    bom_components: List[BOMComponent]
    component_availability: list
    shortages: list
    location_name: Optional[str]


# ============================================================================
# BATCH FEASIBILITY MODELS
# ============================================================================

class BatchFeasibilityItem(BaseModel):
    sku: str
    desired_quantity: int = Field(ge=1)

class BatchFeasibilityRequest(BaseModel):
    items: List[BatchFeasibilityItem] = Field(min_length=1, max_length=50)
    location_name: Optional[str] = None

class MaterialContention(BaseModel):
    component_sku: str
    component_name: str
    total_available: float
    total_demanded: float
    shortage: float
    demanded_by: List[dict]  # [{ sku, quantity_needed }]

class BatchItemResult(BaseModel):
    item_sku: str
    item_name: str
    desired_quantity: int
    can_produce: bool
    max_quantity_producible: int
    limiting_component: Optional[str]
    shortages: list
    status: str  # "fully_producible" | "partially_producible" | "blocked"

class BatchFeasibilityResponse(BaseModel):
    results: List[BatchItemResult]
    material_contentions: List[MaterialContention]
    summary: dict  # { total_skus, fully_producible, partially_producible, blocked, contention_count }


@router.get("/feasibility/{item_identifier}", response_model=ProductionAnalysisResponse)
async def get_production_feasibility(
    request: Request,
    item_identifier: str,
    desired_quantity: int = Query(1, ge=1, description="Desired quantity to produce"),
    current_user: User = Depends(get_current_user),
    location_name: Optional[str] = None,
    production_service: ProductionService = Depends(get_production_service),
):
    try:
        validate_suiteql_identifier(item_identifier, "item_identifier")
        if location_name:
            validate_suiteql_identifier(location_name, "location_name")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    request_start = time.time()
    try:
        logger.info(f"[ROUTER] Checking production feasibility for {item_identifier}, quantity {desired_quantity}")

        analysis = await production_service.get_production_analysis(item_identifier, desired_quantity, location_name)

        request.state.production_data = {
            "item_sku": analysis.get("item_sku", ""),
            "desired_quantity": str(desired_quantity),
            "max_producible": str(analysis.get("max_quantity_producible", "")),
            "can_produce": str(analysis.get("can_produce", "")),
            "limiting_component": analysis.get("limiting_component", ""),
            "shortages_count": str(len(analysis.get("shortages", [])))
        }

        elapsed = time.time() - request_start
        logger.info(f"[ROUTER] Total request took {elapsed:.3f}s")

        return analysis

    except ValueError as e:
        request.state.production_data = {
            "item_sku": item_identifier,
            "desired_quantity": str(desired_quantity),
            "max_producible": "0",
            "can_produce": "False",
            "limiting_component": "Item not found",
            "shortages_count": "0"
        }
        logger.warning(f"Item not found: {e}")
        raise HTTPException(status_code=404, detail=str(e))

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error checking production feasibility: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to check production feasibility")


@router.get("/capacity/{item_identifier}")
async def get_production_capacity(
    request: Request,
    item_identifier: str,
    location_name: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    production_service: ProductionService = Depends(get_production_service),
):
    try:
        validate_suiteql_identifier(item_identifier, "item_identifier")
        if location_name:
            validate_suiteql_identifier(location_name, "location_name")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    request_start = time.time()
    try:
        logger.info(f"[ROUTER] Getting production capacity for {item_identifier}")

        analysis = await production_service.get_production_analysis(item_identifier, 1, location_name)

        request.state.production_data = {
            "item_sku": analysis.get("item_sku", ""),
            "desired_quantity": "1",
            "max_producible": str(analysis.get("max_quantity_producible", "")),
            "can_produce": str(analysis.get("max_quantity_producible", 0) > 0),
            "limiting_component": analysis.get("limiting_component", ""),
            "shortages_count": "0"
        }

        elapsed = time.time() - request_start
        logger.info(f"[ROUTER] Capacity request took {elapsed:.3f}s")

        return {
            "item_id": analysis.get("item_id"),
            "item_name": analysis.get("item_name"),
            "item_sku": analysis.get("item_sku"),
            "max_quantity_producible": analysis.get("max_quantity_producible", 0),
            "limiting_component": analysis.get("limiting_component"),
            "can_produce": analysis.get("max_quantity_producible", 0) > 0,
            "location_name": location_name,
        }

    except ValueError as e:
        request.state.production_data = {
            "item_sku": item_identifier,
            "desired_quantity": "1",
            "max_producible": "0",
            "can_produce": "False",
            "limiting_component": "Item not found",
            "shortages_count": "0"
        }
        logger.warning(f"Item not found: {e}")
        raise HTTPException(status_code=404, detail=str(e))

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error getting production capacity: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get production capacity")


@router.get("/shortages/{item_identifier}")
async def get_production_shortages(
    request: Request,
    item_identifier: str,
    desired_quantity: int = Query(1, ge=1, description="Desired quantity to produce"),
    current_user: User = Depends(get_current_user),
    location_name: Optional[str] = None,
    production_service: ProductionService = Depends(get_production_service),
):
    try:
        validate_suiteql_identifier(item_identifier, "item_identifier")
        if location_name:
            validate_suiteql_identifier(location_name, "location_name")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    request_start = time.time()
    try:
        logger.info(f"[ROUTER] Getting production shortages for {item_identifier}, quantity {desired_quantity}")

        analysis = await production_service.get_production_analysis(item_identifier, desired_quantity, location_name)

        request.state.production_data = {
            "item_sku": analysis.get("item_sku", ""),
            "desired_quantity": str(desired_quantity),
            "max_producible": str(analysis.get("max_quantity_producible", "")),
            "can_produce": str(analysis.get("can_produce", "")),
            "limiting_component": analysis.get("limiting_component", ""),
            "shortages_count": str(len(analysis.get("shortages", [])))
        }

        elapsed = time.time() - request_start
        logger.info(f"[ROUTER] Shortages request took {elapsed:.3f}s")

        return {
            "item_id": analysis.get("item_id"),
            "item_name": analysis.get("item_name"),
            "item_sku": analysis.get("item_sku"),
            "desired_quantity": desired_quantity,
            "can_produce": analysis.get("can_produce", False),
            "shortages": analysis.get("shortages", []),
            "total_shortages": len(analysis.get("shortages", [])),
            "location_name": location_name,
        }

    except ValueError as e:
        logger.warning(f"Item not found: {e}")
        raise HTTPException(status_code=404, detail=str(e))

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error getting production shortages: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get production shortages")


# ============================================================================
# BATCH FEASIBILITY ENDPOINT
# ============================================================================

@router.post("/batch-feasibility", response_model=BatchFeasibilityResponse)
async def get_batch_feasibility(
    request: Request,
    body: BatchFeasibilityRequest,
    current_user: User = Depends(get_current_user),
    production_service: ProductionService = Depends(get_production_service),
):
    """Analyze production feasibility for multiple SKUs with shared material detection."""
    request_start = time.time()
    try:
        logger.info(f"[ROUTER] Batch feasibility request for {len(body.items)} SKUs")

        result = await production_service.get_batch_production_analysis(
            items=[(item.sku, item.desired_quantity) for item in body.items],
            location_name=body.location_name,
        )

        elapsed = time.time() - request_start
        logger.info(f"[ROUTER] Batch feasibility took {elapsed:.3f}s")

        return result

    except Exception as e:
        logger.error(f"Error in batch feasibility: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to analyze batch feasibility")


# ============================================================================
# CACHE MANAGEMENT ENDPOINTS
# ============================================================================

@router.get("/cache/stats")
async def get_cache_stats(
    current_user: User = Depends(get_admin_user),
    production_service: ProductionService = Depends(get_production_service),
):
    """Get cache statistics to monitor performance"""
    try:
        stats = await production_service.get_cache_stats()
        return {
            "cache_enabled": production_service.cache_manager is not None,
            "statistics": stats
        }
    except Exception as e:
        logger.error(f"Error getting cache stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get cache stats")


@router.post("/cache/invalidate/{item_id}")
async def invalidate_item_cache(
    item_id: str,
    item_sku: Optional[str] = None,
    current_user: User = Depends(get_admin_user),
    production_service: ProductionService = Depends(get_production_service),
):
    """Invalidate cache for a specific item (use when BOM changes)"""
    try:
        await production_service.invalidate_item_cache(item_id, item_sku)
        return {
            "message": f"Cache invalidated for item {item_id}",
            "item_id": item_id,
            "item_sku": item_sku
        }
    except Exception as e:
        logger.error(f"Error invalidating cache: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to invalidate cache")


@router.post("/cache/clear")
async def clear_all_caches(
    current_user: User = Depends(get_admin_user),
    production_service: ProductionService = Depends(get_production_service),
):
    """Clear all caches (use sparingly)"""
    try:
        await production_service.clear_all_caches()
        return {"message": "All caches cleared successfully"}
    except Exception as e:
        logger.error(f"Error clearing caches: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to clear caches")
