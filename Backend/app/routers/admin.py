"""
Admin Router - User, Item, and Audit Log management.
All endpoints require admin role.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies.auth import get_admin_user
from app.database.connection import get_db
from app.models.user import User
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


def _validate_admin_password(password: str) -> None:
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    if not any(c.isupper() for c in password):
        raise HTTPException(status_code=400, detail="Password must contain at least one uppercase letter")
    if not any(c.isdigit() for c in password):
        raise HTTPException(status_code=400, detail="Password must contain at least one digit")
    if all(c.isalnum() for c in password):
        raise HTTPException(status_code=400, detail="Password must contain at least one special character")


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
    _validate_admin_password(body.password)

    user = await repo_create(db, body.email, body.username, body.password, body.role)

    from app.utils.audit import log_audit_event
    await log_audit_event(admin.id, "user_created", f"Created user '{body.username}' ({body.email}) with role '{body.role}'")

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

    # Validate password strength if being updated
    if "password" in updates:
        _validate_admin_password(updates["password"])

    user = await repo_update(db, user_id, **updates)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    from app.utils.audit import log_audit_event
    changed = ", ".join(updates.keys())
    if "password" in updates:
        await log_audit_event(admin.id, "admin_password_reset", f"Reset password for user '{user.email}'")
    else:
        await log_audit_event(admin.id, "user_updated", f"Updated user '{user.email}' ({changed})")

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

    # Get user info before deleting for the audit log
    from app.database.repositories.user_repo import get_user_by_id
    target_user = await get_user_by_id(db, user_id)

    success = await repo_delete(db, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")

    from app.utils.audit import log_audit_event
    target_email = target_user.email if target_user else f"ID {user_id}"
    await log_audit_event(admin.id, "user_deleted", f"Deleted user '{target_email}'")

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

    from app.utils.audit import log_audit_event
    await log_audit_event(admin.id, "item_created", f"Created item '{body.sku}' (ID: {body.id})")

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

    from app.utils.audit import log_audit_event
    await log_audit_event(admin.id, "item_updated", f"Updated item '{item.sku}' (ID: {item_id})")

    return {"id": item.id, "sku": item.sku, "name": item.name}


@router.delete("/items/{item_id}")
async def delete_item(
    item_id: int,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    from app.database.repositories.item_repo import delete_item as repo_delete

    # Get item info before deleting for audit
    from app.database.repositories.item_repo import get_item_by_id as get_item
    target_item = await get_item(db, item_id)

    success = await repo_delete(db, item_id)
    if not success:
        raise HTTPException(status_code=404, detail="Item not found")

    from app.utils.audit import log_audit_event
    item_sku = target_item.sku if target_item else f"ID {item_id}"
    await log_audit_event(admin.id, "item_deleted", f"Deleted item '{item_sku}' (ID: {item_id})")

    return {"message": "Item deleted"}


class BulkImportItem(BaseModel):
    id: int
    sku: str
    name: Optional[str] = None


class BulkImportRequest(BaseModel):
    items: List[BulkImportItem]


@router.post("/items/bulk-import")
async def bulk_import_items(
    body: BulkImportRequest,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    from app.database.repositories.item_repo import upsert_item
    from sqlalchemy.exc import IntegrityError

    success_count = 0
    errors = []

    for idx, item in enumerate(body.items):
        try:
            savepoint = await db.begin_nested()
            await upsert_item(db, item.id, item.sku, item.name)
            await savepoint.commit()
            success_count += 1
        except ValueError as e:
            await savepoint.rollback()
            errors.append({
                "row": idx + 2,
                "data": {"id": str(item.id), "sku": item.sku, "name": item.name or ""},
                "error": str(e),
            })
        except IntegrityError as e:
            await savepoint.rollback()
            detail = str(e.orig) if e.orig else str(e)
            if "unique" in detail.lower() or "duplicate" in detail.lower():
                msg = f"Duplicate entry: ID {item.id} or SKU '{item.sku}' already exists"
            else:
                msg = f"Database constraint violation for SKU '{item.sku}'"
            errors.append({
                "row": idx + 2,
                "data": {"id": str(item.id), "sku": item.sku, "name": item.name or ""},
                "error": msg,
            })
        except Exception as e:
            await savepoint.rollback()
            logger.error(f"Bulk import error row {idx+2}: {e}")
            errors.append({
                "row": idx + 2,
                "data": {"id": str(item.id), "sku": item.sku, "name": item.name or ""},
                "error": f"Import failed for SKU '{item.sku}'",
            })

    from app.utils.audit import log_audit_event
    total = len(body.items)
    fail_count = len(errors)
    await log_audit_event(admin.id, "items_imported", f"Bulk CSV import: {success_count}/{total} succeeded, {fail_count} failed")

    return {
        "success_count": success_count,
        "total": total,
        "errors": errors,
    }


# ============================================================================
# API KEY MANAGEMENT
# ============================================================================

class CreateAPIKeyRequest(BaseModel):
    name: str


@router.get("/api-keys")
async def list_api_keys(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    from app.database.repositories.api_key_repo import get_all_api_keys

    result = await get_all_api_keys(db, page, per_page)
    return {
        "api_keys": [
            {
                "id": k.id,
                "name": k.name,
                "key_prefix": k.key_prefix,
                "is_active": k.is_active,
                "created_by": k.created_by,
                "created_at": k.created_at.isoformat() if k.created_at else None,
                "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
            }
            for k in result["api_keys"]
        ],
        "total": result["total"],
        "page": result["page"],
        "per_page": result["per_page"],
    }


@router.post("/api-keys")
async def create_api_key(
    body: CreateAPIKeyRequest,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    from app.database.repositories.api_key_repo import create_api_key as repo_create

    if not body.name or not body.name.strip():
        raise HTTPException(status_code=400, detail="Key name is required")

    api_key, raw_key = await repo_create(db, body.name.strip(), admin.id)

    from app.utils.audit import log_audit_event
    await log_audit_event(admin.id, "api_key_created", f"Created API key '{body.name.strip()}' (prefix: {api_key.key_prefix})")

    return {
        "id": api_key.id,
        "name": api_key.name,
        "key": raw_key,
        "key_prefix": api_key.key_prefix,
        "created_at": api_key.created_at.isoformat() if api_key.created_at else None,
        "message": "Save this key now. It cannot be retrieved again.",
    }


@router.put("/api-keys/{key_id}/revoke")
async def revoke_api_key(
    key_id: int,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    from app.database.repositories.api_key_repo import revoke_api_key as repo_revoke

    success = await repo_revoke(db, key_id)
    if not success:
        raise HTTPException(status_code=404, detail="API key not found")

    from app.utils.audit import log_audit_event
    await log_audit_event(admin.id, "api_key_revoked", f"Revoked API key ID {key_id}")

    return {"message": "API key revoked"}


@router.put("/api-keys/{key_id}/activate")
async def activate_api_key(
    key_id: int,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    from app.database.repositories.api_key_repo import activate_api_key as repo_activate

    success = await repo_activate(db, key_id)
    if not success:
        raise HTTPException(status_code=404, detail="API key not found")

    from app.utils.audit import log_audit_event
    await log_audit_event(admin.id, "api_key_activated", f"Activated API key ID {key_id}")

    return {"message": "API key activated"}


@router.delete("/api-keys/{key_id}")
async def delete_api_key(
    key_id: int,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    from app.database.repositories.api_key_repo import delete_api_key as repo_delete

    success = await repo_delete(db, key_id)
    if not success:
        raise HTTPException(status_code=404, detail="API key not found")

    from app.utils.audit import log_audit_event
    await log_audit_event(admin.id, "api_key_deleted", f"Deleted API key ID {key_id}")

    return {"message": "API key deleted"}


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
    from sqlalchemy import select, func, desc, union_all, literal, cast, String
    from app.database.models import AuditEventDB, RequestLogDB, UserDB

    # Build unified query: audit events + production checks
    audit_q = (
        select(
            AuditEventDB.timestamp.label("timestamp"),
            AuditEventDB.user_id.label("user_id"),
            UserDB.username.label("username"),
            AuditEventDB.action.label("action"),
            AuditEventDB.details.label("details"),
        )
        .outerjoin(UserDB, AuditEventDB.user_id == UserDB.id)
    )

    production_q = (
        select(
            RequestLogDB.timestamp.label("timestamp"),
            RequestLogDB.user_id.label("user_id"),
            UserDB.username.label("username"),
            literal("production_check").label("action"),
            func.concat(
                'SKU: ', func.coalesce(RequestLogDB.item_sku, '?'),
                ', Qty: ', func.coalesce(RequestLogDB.desired_quantity, '?'),
                ', Producible: ', func.coalesce(RequestLogDB.can_produce, '?'),
                ', Max: ', func.coalesce(RequestLogDB.max_producible, '?'),
            ).label("details"),
        )
        .outerjoin(UserDB, RequestLogDB.user_id == UserDB.id)
        .where(RequestLogDB.item_sku.isnot(None))
    )

    combined = union_all(audit_q, production_q).subquery()

    # Total count
    total_result = await db.execute(select(func.count()).select_from(combined))
    total = total_result.scalar() or 0

    # Paginated results
    result = await db.execute(
        select(combined)
        .order_by(desc(combined.c.timestamp))
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    rows = result.all()

    return {
        "logs": [
            {
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                "user_id": row.user_id,
                "username": row.username,
                "action": row.action,
                "details": row.details,
            }
            for row in rows
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
    }
