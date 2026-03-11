"""
Analytics Router - Top requested items endpoint.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies.auth import get_current_user
from app.database.connection import get_db
from app.models.user import User

router = APIRouter()


@router.get("/top-items")
async def get_top_items(
    limit: int = Query(5, ge=1, le=20),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get top requested items from request logs."""
    from app.database.repositories.log_repo import get_top_requested_items

    items = await get_top_requested_items(db, limit)
    return items
