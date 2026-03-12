"""
Audit event logging utility.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def log_audit_event(user_id: Optional[int], action: str, details: str = None):
    """Log an audit event to the database."""
    try:
        from app.database.connection import get_session_factory
        from app.database.models import AuditEventDB

        factory = get_session_factory()
        async with factory() as session:
            event = AuditEventDB(
                user_id=user_id,
                action=action,
                details=details,
            )
            session.add(event)
            await session.commit()
    except Exception as e:
        logger.error(f"Failed to log audit event: {action} - {e}")
