"""
Admin Router - User, Item, and Audit Log management.
All endpoints require admin role.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies.auth import get_admin_user
from app.database.connection import get_db
from app.models.user import User
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================================
# USER MANAGEMENT
# ============================================================================

class CreateUserRequest(BaseModel):
    email: EmailStr
    username: str
    password: str
    role: str = "user"


class UpdateUserRequest(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None
    disabled: Optional[bool] = None
    password: Optional[str] = None


@router.get("/users")
async def list_users(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    from app.database.repositories.user_repo import get_all_users

    users = await get_all_users(db)
    return [
        {
            "id": u.id,
            "email": u.email,
            "username": u.username,
            "role": u.role,
            "disabled": u.disabled,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "last_login": u.last_login.isoformat() if u.last_login else None,
        }
        for u in users
    ]


@router.post("/users")
async def create_user(
    body: CreateUserRequest,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    from app.database.repositories.user_repo import create_user as repo_create, get_user_by_email

    existing = await get_user_by_email(db, body.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Validate password strength
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    user = await repo_create(db, body.email, body.username, body.password, body.role)
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "role": user.role,
    }


@router.put("/users/{user_id}")
async def update_user(
    user_id: int,
    body: UpdateUserRequest,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    from app.database.repositories.user_repo import update_user as repo_update

    updates = {k: v for k, v in body.dict().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    user = await repo_update(db, user_id, **updates)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "role": user.role,
        "disabled": user.disabled,
    }


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    from app.database.repositories.user_repo import delete_user as repo_delete

    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    success = await repo_delete(db, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")

    return {"message": "User deleted"}


# ============================================================================
# ITEM MANAGEMENT
# ============================================================================

class CreateItemRequest(BaseModel):
    id: int
    sku: str
    name: Optional[str] = None


class UpdateItemRequest(BaseModel):
    sku: Optional[str] = None
    name: Optional[str] = None


@router.get("/items")
async def list_items(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    from app.database.repositories.item_repo import get_all_items

    result = await get_all_items(db, page, per_page, search)
    return {
        "items": [
            {
                "id": item.id,
                "sku": item.sku,
                "name": item.name,
                "created_at": item.created_at.isoformat() if item.created_at else None,
                "updated_at": item.updated_at.isoformat() if item.updated_at else None,
            }
            for item in result["items"]
        ],
        "total": result["total"],
        "page": result["page"],
        "per_page": result["per_page"],
    }


@router.post("/items")
async def create_item(
    body: CreateItemRequest,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    from app.database.repositories.item_repo import upsert_item

    item = await upsert_item(db, body.id, body.sku, body.name)
    return {"id": item.id, "sku": item.sku, "name": item.name}


@router.put("/items/{item_id}")
async def update_item(
    item_id: int,
    body: UpdateItemRequest,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    from app.database.repositories.item_repo import get_item_by_id

    item = await get_item_by_id(db, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    if body.sku is not None:
        item.sku = body.sku
    if body.name is not None:
        item.name = body.name
    await db.flush()

    return {"id": item.id, "sku": item.sku, "name": item.name}


@router.delete("/items/{item_id}")
async def delete_item(
    item_id: int,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    from app.database.repositories.item_repo import delete_item as repo_delete

    success = await repo_delete(db, item_id)
    if not success:
        raise HTTPException(status_code=404, detail="Item not found")

    return {"message": "Item deleted"}


# ============================================================================
# AUDIT LOGS
# ============================================================================

@router.get("/audit-logs")
async def get_audit_logs(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    from app.database.repositories.log_repo import get_audit_logs as repo_audit

    result = await repo_audit(db, page, per_page)
    return {
        "logs": [
            {
                "id": entry["log"].id,
                "timestamp": entry["log"].timestamp.isoformat() if entry["log"].timestamp else None,
                "request_id": entry["log"].request_id,
                "session_id": entry["log"].session_id,
                "user_id": entry["log"].user_id,
                "username": entry["username"],
                "item_sku": entry["log"].item_sku,
                "desired_quantity": entry["log"].desired_quantity,
                "max_producible": entry["log"].max_producible,
                "can_produce": entry["log"].can_produce,
                "limiting_component": entry["log"].limiting_component,
                "shortages_count": entry["log"].shortages_count,
                "response_time_ms": entry["log"].response_time_ms,
                "status_code": entry["log"].status_code,
                "error_type": entry["log"].error_type,
                "error_message": entry["log"].error_message,
                "cache_hit": entry["log"].cache_hit,
            }
            for entry in result["logs"]
        ],
        "total": result["total"],
        "page": result["page"],
        "per_page": result["per_page"],
    }
