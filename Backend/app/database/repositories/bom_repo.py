"""
Repository for the persisted BOM formula cache (bom_formula + bom_component).

Stores each assembly's direct recipe (one level) keyed by NetSuite internal item id, so the
multi-level tree is reconstructed by recursing over these rows locally instead of hitting NetSuite.
"""
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import BOMFormulaDB, BOMComponentDB


async def get_bom_formula(db: AsyncSession, assembly_item_id: int) -> Optional[BOMFormulaDB]:
    result = await db.execute(
        select(BOMFormulaDB).where(BOMFormulaDB.assembly_item_id == assembly_item_id)
    )
    return result.scalar_one_or_none()


async def get_bom_components(db: AsyncSession, assembly_item_id: int) -> List[BOMComponentDB]:
    result = await db.execute(
        select(BOMComponentDB)
        .where(BOMComponentDB.assembly_item_id == assembly_item_id)
        .order_by(BOMComponentDB.ordinal, BOMComponentDB.id)
    )
    return list(result.scalars().all())


async def upsert_bom_formula(
    db: AsyncSession,
    assembly_item_id: int,
    revision_id: Optional[str],
    source: str,
    has_bom: bool,
) -> None:
    """Insert/refresh the formula metadata row, stamping refreshed_at = now."""
    now = datetime.utcnow()
    stmt = insert(BOMFormulaDB).values(
        assembly_item_id=assembly_item_id,
        revision_id=revision_id,
        source=source,
        has_bom=has_bom,
        refreshed_at=now,
        last_error=None,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["assembly_item_id"],
        set_={
            "revision_id": revision_id,
            "source": source,
            "has_bom": has_bom,
            "refreshed_at": now,
            "last_error": None,
        },
    )
    await db.execute(stmt)


async def replace_bom_components(
    db: AsyncSession, assembly_item_id: int, components: List[Dict]
) -> None:
    """Replace the stored direct components for an assembly with a fresh set."""
    await db.execute(
        delete(BOMComponentDB).where(BOMComponentDB.assembly_item_id == assembly_item_id)
    )
    rows = []
    for i, c in enumerate(components):
        internal_id = c.get("internal_id") or c.get("component_item_id")
        try:
            component_item_id = int(internal_id)
        except (TypeError, ValueError):
            continue  # skip components we can't key by id
        name = c.get("component_displayname") or c.get("component_name") or c.get("displayname") or ""
        rows.append(
            BOMComponentDB(
                assembly_item_id=assembly_item_id,
                component_item_id=component_item_id,
                component_sku=c.get("component_sku", ""),
                component_name=name or None,
                quantity=float(c.get("quantity_required", 0) or 0),
                unit=c.get("unit"),
                is_phantom=str(c.get("is_phantom")).lower() == "true",
                is_manufacturing=str(c.get("is_manufacturing")).lower() == "true",
                bom_id=str(c.get("bom_id")) if c.get("bom_id") is not None else None,
                ordinal=i,
            )
        )
    if rows:
        db.add_all(rows)


async def get_all_formula_ids(db: AsyncSession) -> List[int]:
    """All assembly item ids that currently have a cached formula (for a full refresh)."""
    result = await db.execute(select(BOMFormulaDB.assembly_item_id))
    return [row[0] for row in result.all()]


async def delete_bom_formula(db: AsyncSession, assembly_item_id: int) -> None:
    """Remove an item's cached formula (components cascade). Used by cache invalidation."""
    await db.execute(
        delete(BOMFormulaDB).where(BOMFormulaDB.assembly_item_id == assembly_item_id)
    )


async def get_formula_refreshed_map(db: AsyncSession, item_ids: List[int]) -> Dict[int, datetime]:
    """id -> refreshed_at for the given item ids (for the admin 'Formula as of' column)."""
    if not item_ids:
        return {}
    result = await db.execute(
        select(BOMFormulaDB.assembly_item_id, BOMFormulaDB.refreshed_at).where(
            BOMFormulaDB.assembly_item_id.in_(item_ids)
        )
    )
    return {row[0]: row[1] for row in result.all()}
