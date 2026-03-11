"""
CSV Logger Service - Now backed by PostgreSQL.
Keeps same interface for backward compatibility.
"""
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class CSVLogger:
    """Logger that writes to PostgreSQL (kept name for backward compat)."""

    def __init__(self):
        logger.info("CSVLogger initialized (DB-backed)")

    def append_user(self, user_data: Dict[str, Any]) -> bool:
        # User events are now handled by the session service directly
        logger.debug(f"Logged user: {user_data.get('user_id')}")
        return True

    def append_session(self, session_data: Dict[str, Any]) -> bool:
        # Session writes are handled by the background db_writer
        from app.background.db_writer import enqueue_log
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(enqueue_log("session", session_data))
            else:
                loop.run_until_complete(enqueue_log("session", session_data))
        except RuntimeError:
            logger.warning("No event loop available for session log")
        logger.debug(f"Logged session: {session_data.get('session_id')}")
        return True

    def append_request(self, request_data: Dict[str, Any]) -> bool:
        logger.debug(f"Logged request: {request_data.get('request_id')}")
        return True

    def batch_append_requests(self, requests_data: list) -> int:
        logger.debug(f"Batch logged {len(requests_data)} requests")
        return len(requests_data)

    def get_stats(self) -> Dict[str, Any]:
        try:
            import asyncio
            from app.database.connection import get_session_factory
            from app.database.repositories.log_repo import get_log_stats

            async def _get_stats():
                factory = get_session_factory()
                async with factory() as session:
                    return await get_log_stats(session)

            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Can't await in sync context, return placeholder
                return {"note": "Use /admin/logging-stats for async stats"}
            return loop.run_until_complete(_get_stats())
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {}


_csv_logger_instance: Optional[CSVLogger] = None


def get_csv_logger() -> CSVLogger:
    global _csv_logger_instance
    if _csv_logger_instance is None:
        _csv_logger_instance = CSVLogger()
    return _csv_logger_instance


def log_user(user_data: Dict[str, Any]) -> bool:
    return get_csv_logger().append_user(user_data)


def log_session(session_data: Dict[str, Any]) -> bool:
    return get_csv_logger().append_session(session_data)


def log_request(request_data: Dict[str, Any]) -> bool:
    return get_csv_logger().append_request(request_data)


def log_requests_batch(requests_data: list) -> int:
    return get_csv_logger().batch_append_requests(requests_data)
