"""
Item Repository - Database operations for items.
"""
from typing import Optional, List
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import ItemDB


async def get_item_by_sku(db: AsyncSession, sku: str) -> Optional[ItemDB]:
    result = await db.execute(select(ItemDB).where(ItemDB.sku == sku))
    return result.scalar_one_or_none()


async def get_item_by_id(db: AsyncSession, item_id: int) -> Optional[ItemDB]:
    result = await db.execute(select(ItemDB).where(ItemDB.id == item_id))
    return result.scalar_one_or_none()


async def upsert_item(db: AsyncSession, item_id: int, sku: str, name: str = None) -> ItemDB:
    # Check if SKU already exists with a different ID
    existing = await get_item_by_sku(db, sku)
    if existing and existing.id != item_id:
        raise ValueError(
            f"SKU '{sku}' already exists with a different ID (existing ID: {existing.id}, given ID: {item_id})"
        )

    stmt = insert(ItemDB).values(id=item_id, sku=sku, name=name)
    stmt = stmt.on_conflict_do_update(
        index_elements=["id"],
        set_={"sku": sku, "name": name},
    )
    await db.execute(stmt)
    await db.flush()
    return await get_item_by_id(db, item_id)


async def bulk_import_items(db: AsyncSession, items_list: list) -> int:
    """Batch upsert items. Each item: {id, sku, name}."""
    count = 0
    for item in items_list:
        stmt = insert(ItemDB).values(
            id=item["id"], sku=item["sku"], name=item.get("name")
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={"sku": item["sku"], "name": item.get("name")},
        )
        await db.execute(stmt)
        count += 1
    await db.flush()
    return count


async def get_all_items(
    db: AsyncSession, page: int = 1, per_page: int = 20, search: str = None
) -> dict:
    query = select(ItemDB)
    count_query = select(func.count(ItemDB.id))

    if search:
        like = f"%{search}%"
        query = query.where((ItemDB.sku.ilike(like)) | (ItemDB.name.ilike(like)))
        count_query = count_query.where(
            (ItemDB.sku.ilike(like)) | (ItemDB.name.ilike(like))
        )

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    query = query.order_by(ItemDB.id).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return {"items": items, "total": total, "page": page, "per_page": per_page}


async def delete_item(db: AsyncSession, item_id: int) -> bool:
    item = await get_item_by_id(db, item_id)
    if not item:
        return False
    await db.delete(item)
    await db.flush()
    return True


async def search_items(db: AsyncSession, query: str) -> List[ItemDB]:
    like = f"%{query}%"
    result = await db.execute(
        select(ItemDB)
        .where((ItemDB.sku.ilike(like)) | (ItemDB.name.ilike(like)))
        .limit(50)
    )
    return list(result.scalars().all())
