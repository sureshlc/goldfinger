"""
Seed Items Script - Import items from CSV to PostgreSQL.
Run: python -m app.database.seed_items
"""
import asyncio
import csv
from pathlib import Path
from app.database.connection import init_db, close_db, get_session_factory
from app.database.repositories.item_repo import bulk_import_items


async def seed():
    await init_db()
    factory = get_session_factory()

    csv_path = Path("app/data/items.csv")
    if not csv_path.exists():
        print(f"ERROR: {csv_path} not found")
        return

    items = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            item_id = row.get("id", "").strip()
            sku = row.get("sku", "").strip()
            name = row.get("name", "").strip()
            if item_id and sku:
                items.append({"id": int(item_id), "sku": sku, "name": name or None})

    print(f"\nImporting {len(items)} items from {csv_path}...")

    async with factory() as session:
        count = await bulk_import_items(session, items)
        await session.commit()

    print(f"Imported {count} items successfully.\n")
    await close_db()


if __name__ == "__main__":
    asyncio.run(seed())
