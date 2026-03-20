"""
API Key Repository - Database operations for API key management.
"""
import hashlib
import secrets
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import APIKeyDB


async def create_api_key(db: AsyncSession, name: str, created_by: int) -> tuple[APIKeyDB, str]:
    """Create a new API key. Returns (db_record, raw_key). Raw key is shown once."""
    raw_key = "gf_" + secrets.token_hex(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_prefix = raw_key[:11]

    api_key = APIKeyDB(
        name=name,
        key_hash=key_hash,
        key_prefix=key_prefix,
        created_by=created_by,
        is_active=True,
    )
    db.add(api_key)
    await db.flush()
    await db.refresh(api_key)
    return api_key, raw_key


async def get_all_api_keys(db: AsyncSession, page: int = 1, per_page: int = 20) -> dict:
    """List all API keys (without hashes). Paginated."""
    total_result = await db.execute(select(func.count()).select_from(APIKeyDB))
    total = total_result.scalar() or 0

    result = await db.execute(
        select(APIKeyDB)
        .order_by(APIKeyDB.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    keys = list(result.scalars().all())

    return {
        "api_keys": keys,
        "total": total,
        "page": page,
        "per_page": per_page,
    }


async def get_api_key_by_hash(db: AsyncSession, key_hash: str) -> Optional[APIKeyDB]:
    """Look up an API key by its hash. Used during authentication."""
    result = await db.execute(select(APIKeyDB).where(APIKeyDB.key_hash == key_hash))
    return result.scalar_one_or_none()


async def update_last_used(db: AsyncSession, key_id: int) -> None:
    """Update last_used_at timestamp."""
    await db.execute(
        update(APIKeyDB)
        .where(APIKeyDB.id == key_id)
        .values(last_used_at=datetime.now(timezone.utc))
    )
    await db.flush()


async def revoke_api_key(db: AsyncSession, key_id: int) -> bool:
    """Soft-revoke: set is_active = False."""
    key = await db.execute(select(APIKeyDB).where(APIKeyDB.id == key_id))
    api_key = key.scalar_one_or_none()
    if not api_key:
        return False
    api_key.is_active = False
    await db.flush()
    return True


async def activate_api_key(db: AsyncSession, key_id: int) -> bool:
    """Re-activate a revoked key."""
    key = await db.execute(select(APIKeyDB).where(APIKeyDB.id == key_id))
    api_key = key.scalar_one_or_none()
    if not api_key:
        return False
    api_key.is_active = True
    await db.flush()
    return True


async def delete_api_key(db: AsyncSession, key_id: int) -> bool:
    """Hard delete an API key."""
    key = await db.execute(select(APIKeyDB).where(APIKeyDB.id == key_id))
    api_key = key.scalar_one_or_none()
    if not api_key:
        return False
    await db.delete(api_key)
    await db.flush()
    return True
