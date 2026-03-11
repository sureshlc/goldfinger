"""
Log Repository - Database operations for request and session logs.
"""
from typing import Optional
from datetime import datetime
from dateutil import parser as dateparser
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import RequestLogDB, SessionDB


def _parse_dt(value) -> Optional[datetime]:
    """Parse a datetime from string or return as-is if already datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return dateparser.isoparse(value)
        except (ValueError, TypeError):
            return None
    return None


def _safe_int(value) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _safe_float(value) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


async def insert_request_log(db: AsyncSession, log_data: dict) -> RequestLogDB:
    log = RequestLogDB(
        timestamp=_parse_dt(log_data.get("timestamp")) or datetime.utcnow(),
        request_id=log_data.get("request_id") or None,
        session_id=log_data.get("session_id") or None,
        user_id=_safe_int(log_data.get("user_id")),
        item_sku=log_data.get("item_sku") or None,
        desired_quantity=log_data.get("desired_quantity") or None,
        max_producible=log_data.get("max_producible") or None,
        can_produce=log_data.get("can_produce") or None,
        limiting_component=log_data.get("limiting_component") or None,
        shortages_count=log_data.get("shortages_count") or None,
        response_time_ms=_safe_float(log_data.get("response_time_ms")),
        status_code=_safe_int(log_data.get("status_code")),
        error_type=log_data.get("error_type") or None,
        error_message=log_data.get("error_message") or None,
        cache_hit=log_data.get("cache_hit") or None,
        location=log_data.get("location") or None,
    )
    db.add(log)
    await db.flush()
    return log


async def batch_insert_request_logs(db: AsyncSession, logs: list) -> int:
    count = 0
    for log_data in logs:
        await insert_request_log(db, log_data)
        count += 1
    await db.flush()
    return count


async def insert_session_log(db: AsyncSession, session_data: dict) -> SessionDB:
    session_log = SessionDB(
        session_id=session_data["session_id"],
        user_id=_safe_int(session_data["user_id"]),
        login_time=_parse_dt(session_data.get("login_time")) or datetime.utcnow(),
        logout_time=_parse_dt(session_data.get("logout_time")),
        session_duration_mins=_safe_float(session_data.get("session_duration_mins")),
        total_requests=_safe_int(session_data.get("total_requests")) or 0,
        status=session_data.get("status", "active"),
    )
    db.add(session_log)
    await db.flush()
    return session_log


async def update_session_log(db: AsyncSession, session_id: str, session_data: dict):
    """Update an existing session log (e.g. on logout)."""
    result = await db.execute(
        select(SessionDB).where(SessionDB.session_id == session_id)
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.logout_time = _parse_dt(session_data.get("logout_time"))
        existing.session_duration_mins = _safe_float(session_data.get("session_duration_mins"))
        existing.total_requests = _safe_int(session_data.get("total_requests")) or existing.total_requests
        existing.status = session_data.get("status", existing.status)
        await db.flush()
    else:
        await insert_session_log(db, session_data)


async def get_log_stats(db: AsyncSession) -> dict:
    req_count = await db.execute(select(func.count(RequestLogDB.id)))
    sess_count = await db.execute(select(func.count(SessionDB.id)))
    return {
        "requests_count": req_count.scalar() or 0,
        "sessions_count": sess_count.scalar() or 0,
    }


async def get_audit_logs(
    db: AsyncSession, page: int = 1, per_page: int = 50
) -> dict:
    from app.database.models import UserDB

    total_result = await db.execute(select(func.count(RequestLogDB.id)))
    total = total_result.scalar() or 0

    result = await db.execute(
        select(RequestLogDB, UserDB.username)
        .outerjoin(UserDB, RequestLogDB.user_id == UserDB.id)
        .order_by(desc(RequestLogDB.timestamp))
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    rows = result.all()
    logs = [{"log": row[0], "username": row[1]} for row in rows]

    return {"logs": logs, "total": total, "page": page, "per_page": per_page}


async def get_top_requested_items(db: AsyncSession, limit: int = 5) -> list:
    from app.database.models import ItemDB

    result = await db.execute(
        select(
            RequestLogDB.item_sku,
            func.count(RequestLogDB.id).label("request_count"),
            func.max(RequestLogDB.timestamp).label("last_requested"),
            func.max(ItemDB.name).label("item_name"),
        )
        .outerjoin(ItemDB, RequestLogDB.item_sku == ItemDB.sku)
        .where(RequestLogDB.item_sku.isnot(None))
        .where(RequestLogDB.item_sku != "")
        .where(RequestLogDB.status_code == 200)
        .group_by(RequestLogDB.item_sku)
        .order_by(desc(func.count(RequestLogDB.id)))
        .limit(limit)
    )
    rows = result.all()
    return [
        {
            "item_sku": row.item_sku,
            "item_name": row.item_name,
            "request_count": row.request_count,
            "last_requested": row.last_requested.isoformat() if row.last_requested else None,
        }
        for row in rows
    ]
