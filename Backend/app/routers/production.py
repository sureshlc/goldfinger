from fastapi import APIRouter, HTTPException, Query, Depends, Request
from typing import Optional, List
import asyncio
import csv
import io
import logging
import time
from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from app.services.production_service import ProductionService
from app.services.service_registry import get_production_service, get_bom_service
from app.utils.suiteql_sanitizer import validate_suiteql_identifier
from app.utils.email_sender import EmailNotConfiguredError, send_email
from app.dependencies.auth import get_current_user, get_admin_user
from app.models.user import User
from app.config import settings

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
    unit: Optional[str] = ""

class MaterialSummary(BaseModel):
    component_sku: str
    component_name: str
    unit: Optional[str] = ""
    total_demanded: float
    total_available: float
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
    material_summary: List[MaterialSummary] = []
    summary: dict  # { total_skus, fully_producible, partially_producible, blocked, contention_count }

class EmailFeasibilityRequest(BaseModel):
    items: List[BatchFeasibilityItem] = Field(min_length=1, max_length=50)
    location_name: Optional[str] = None
    recipients: List[EmailStr] = Field(min_length=1, max_length=10)
    subject: Optional[str] = None
    note: Optional[str] = None

class EmailFeasibilityResponse(BaseModel):
    sent: bool
    recipients_count: int


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


def _materials_to_csv(material_summary: List[dict]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Component SKU",
        "Component Name",
        "Unit",
        "Total Demanded",
        "Total Available",
        "Shortage",
        "Affected SKUs",
    ])
    for m in material_summary:
        affected = ", ".join(d.get("sku", "") for d in m.get("demanded_by", []))
        writer.writerow([
            m.get("component_sku", ""),
            m.get("component_name", ""),
            m.get("unit", ""),
            f"{m.get('total_demanded', 0):.4f}".rstrip("0").rstrip("."),
            f"{m.get('total_available', 0):.4f}".rstrip("0").rstrip("."),
            f"{m.get('shortage', 0):.4f}".rstrip("0").rstrip("."),
            affected,
        ])
    return buf.getvalue().encode("utf-8")


def _build_email_html(report: dict, batch_items: List[BatchFeasibilityItem], note: Optional[str]) -> str:
    summary = report.get("summary", {}) or {}
    materials = report.get("material_summary", []) or []
    short_rows = [m for m in materials if (m.get("shortage", 0) or 0) > 0]
    fully = summary.get("fully_producible", 0)
    partial = summary.get("partially_producible", 0)
    blocked = summary.get("blocked", 0)

    items_listing = "".join(
        f"<li><strong>{i.sku.upper()}</strong> &times; {i.desired_quantity}</li>"
        for i in batch_items
    )

    short_rows_html = "".join(
        f"<tr>"
        f"<td style='padding:6px 8px;border:1px solid #e5e7eb;'>{m.get('component_sku','')}</td>"
        f"<td style='padding:6px 8px;border:1px solid #e5e7eb;'>{m.get('component_name','')}</td>"
        f"<td style='padding:6px 8px;border:1px solid #e5e7eb;text-align:right;'>{m.get('total_demanded',0):g} {m.get('unit','')}</td>"
        f"<td style='padding:6px 8px;border:1px solid #e5e7eb;text-align:right;'>{m.get('total_available',0):g} {m.get('unit','')}</td>"
        f"<td style='padding:6px 8px;border:1px solid #e5e7eb;text-align:right;color:#b91c1c;font-weight:600;'>{m.get('shortage',0):g} {m.get('unit','')}</td>"
        f"</tr>"
        for m in short_rows
    ) or "<tr><td colspan='5' style='padding:8px;color:#16a34a;'>No shortages — all materials available.</td></tr>"

    note_block = f"<p style='margin:0 0 12px 0;color:#374151;'><em>{note}</em></p>" if note else ""

    return f"""
    <html><body style='font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#111827;'>
      <h2 style='margin:0 0 8px 0;'>Production Feasibility Report</h2>
      <p style='margin:0 0 12px 0;color:#6b7280;font-size:13px;'>Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</p>
      {note_block}
      <h3 style='margin:16px 0 4px 0;'>Batch</h3>
      <ul style='margin:0 0 12px 16px;'>{items_listing}</ul>
      <p style='margin:0 0 12px 0;'>
        <strong>{fully}</strong> fully producible &middot;
        <strong>{partial}</strong> partial &middot;
        <strong>{blocked}</strong> blocked
      </p>
      <h3 style='margin:16px 0 4px 0;'>Material shortages</h3>
      <table style='border-collapse:collapse;font-size:13px;'>
        <thead>
          <tr style='background:#f9fafb;'>
            <th style='padding:6px 8px;border:1px solid #e5e7eb;text-align:left;'>SKU</th>
            <th style='padding:6px 8px;border:1px solid #e5e7eb;text-align:left;'>Name</th>
            <th style='padding:6px 8px;border:1px solid #e5e7eb;text-align:right;'>Demanded</th>
            <th style='padding:6px 8px;border:1px solid #e5e7eb;text-align:right;'>Available</th>
            <th style='padding:6px 8px;border:1px solid #e5e7eb;text-align:right;'>Short</th>
          </tr>
        </thead>
        <tbody>{short_rows_html}</tbody>
      </table>
      <p style='margin:12px 0 0 0;color:#6b7280;font-size:12px;'>
        Full materials list (including sufficient items) is attached as CSV.
      </p>
    </body></html>
    """


@router.post("/batch-feasibility/email", response_model=EmailFeasibilityResponse)
async def email_batch_feasibility(
    body: EmailFeasibilityRequest,
    current_user: User = Depends(get_current_user),
    production_service: ProductionService = Depends(get_production_service),
):
    """Run batch feasibility and email the report (CSV attached) to the given recipients."""
    if not settings.email_configured:
        raise HTTPException(
            status_code=503,
            detail="Email is not configured. Contact an admin to set up SMTP.",
        )

    try:
        report = await production_service.get_batch_production_analysis(
            items=[(item.sku, item.desired_quantity) for item in body.items],
            location_name=body.location_name,
        )

        csv_bytes = _materials_to_csv(report.get("material_summary", []) or [])
        html = _build_email_html(report, body.items, body.note)
        subject = body.subject or f"Production Feasibility Report — {len(body.items)} SKU(s)"
        filename = f"materials-{datetime.utcnow().strftime('%Y-%m-%d')}.csv"

        await asyncio.to_thread(
            send_email,
            settings,
            list(body.recipients),
            subject,
            html,
            None,
            [(filename, csv_bytes, "text/csv")],
        )
        return EmailFeasibilityResponse(sent=True, recipients_count=len(body.recipients))
    except EmailNotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending batch feasibility email: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to send report email")


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
