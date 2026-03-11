"""
Background DB Writer Service
Handles async batch writing of logs to PostgreSQL using AsyncIO queue.
"""
import asyncio
from typing import Dict, Any, Optional
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Global queue for log events
log_queue: Optional[asyncio.Queue] = None

# Background worker task reference
_worker_task: Optional[asyncio.Task] = None

# Batch configuration
BATCH_SIZE = 50
BATCH_TIMEOUT = 5.0
QUEUE_MAX_SIZE = 10000


class LogEvent:
    def __init__(self, event_type: str, data: Dict[str, Any]):
        self.event_type = event_type
        self.data = data
        self.timestamp = datetime.utcnow()


def init_log_queue():
    global log_queue
    if log_queue is None:
        log_queue = asyncio.Queue(maxsize=QUEUE_MAX_SIZE)
        logger.info(f"Log queue initialized (max_size={QUEUE_MAX_SIZE})")


async def enqueue_log(event_type: str, data: Dict[str, Any]) -> bool:
    global log_queue
    if log_queue is None:
        logger.warning("Log queue not initialized, initializing now")
        init_log_queue()
    try:
        event = LogEvent(event_type, data)
        log_queue.put_nowait(event)
        return True
    except asyncio.QueueFull:
        logger.error(f"Log queue full! Dropping {event_type} event")
        return False
    except Exception as e:
        logger.error(f"Failed to enqueue log: {e}")
        return False


async def _write_to_db(event_type: str, data: dict):
    """Write a single event to database."""
    try:
        from app.database.connection import get_session_factory
        from app.database.repositories.log_repo import (
            insert_request_log,
            insert_session_log,
            update_session_log,
        )

        factory = get_session_factory()
        async with factory() as session:
            if event_type == "request":
                await insert_request_log(session, data)
            elif event_type == "session":
                if data.get("status") == "completed":
                    await update_session_log(session, data["session_id"], data)
                else:
                    await insert_session_log(session, data)
            await session.commit()
    except Exception as e:
        logger.error(f"Failed to write {event_type} to DB: {e}")


async def _batch_write_requests(requests_data: list):
    """Batch write request logs to database."""
    try:
        from app.database.connection import get_session_factory
        from app.database.repositories.log_repo import batch_insert_request_logs

        factory = get_session_factory()
        async with factory() as session:
            count = await batch_insert_request_logs(session, requests_data)
            await session.commit()
            logger.debug(f"Batch wrote {count} requests to DB")
    except Exception as e:
        logger.error(f"Failed to batch write requests to DB: {e}")


async def db_writer_worker():
    """Background worker that processes log queue and writes to PostgreSQL."""
    global log_queue
    logger.info("DB writer worker started")
    request_batch = []

    try:
        while True:
            try:
                event = await asyncio.wait_for(log_queue.get(), timeout=1.0)

                if event.event_type == "user":
                    # User events are handled by session service, skip
                    pass
                elif event.event_type == "session":
                    await _write_to_db("session", event.data)
                elif event.event_type == "request":
                    request_batch.append(event.data)
                    if len(request_batch) >= BATCH_SIZE:
                        await _batch_write_requests(request_batch)
                        request_batch.clear()

                log_queue.task_done()

            except asyncio.TimeoutError:
                if request_batch:
                    await _batch_write_requests(request_batch)
                    request_batch.clear()
                continue

            except Exception as e:
                logger.error(f"Error processing log event: {e}")

    except asyncio.CancelledError:
        logger.info("DB writer worker shutting down...")
        if request_batch:
            await _batch_write_requests(request_batch)

        remaining = 0
        max_flush = 100
        while not log_queue.empty() and remaining < max_flush:
            try:
                event = log_queue.get_nowait()
                if event.event_type == "session":
                    await _write_to_db("session", event.data)
                elif event.event_type == "request":
                    await _write_to_db("request", event.data)
                log_queue.task_done()
                remaining += 1
            except asyncio.QueueEmpty:
                break
            except Exception as e:
                logger.error(f"Error flushing event during shutdown: {e}")
                break

        if remaining > 0:
            logger.info(f"Flushed {remaining} remaining log events")
        logger.info("DB writer worker stopped")
        raise


async def start_db_writer():
    global _worker_task, log_queue
    if _worker_task is not None:
        logger.warning("DB writer worker already running")
        return
    if log_queue is None:
        init_log_queue()
    _worker_task = asyncio.create_task(db_writer_worker())
    logger.info("DB writer background task started")


async def stop_db_writer(timeout: float = 5.0):
    global _worker_task, log_queue
    if _worker_task is None:
        logger.warning("DB writer worker not running")
        return
    logger.info("Stopping DB writer worker...")
    _worker_task.cancel()
    try:
        await asyncio.wait_for(_worker_task, timeout=timeout)
    except asyncio.CancelledError:
        logger.info("Worker cancelled successfully")
    except asyncio.TimeoutError:
        logger.warning(f"Worker shutdown timed out after {timeout}s")
    except Exception as e:
        logger.error(f"Error during worker shutdown: {e}")
    _worker_task = None
    logger.info("DB writer worker stopped successfully")


async def get_queue_stats() -> Dict[str, Any]:
    global log_queue
    if log_queue is None:
        return {"queue_initialized": False, "queue_size": 0, "queue_max_size": 0}
    return {
        "queue_initialized": True,
        "queue_size": log_queue.qsize(),
        "queue_max_size": QUEUE_MAX_SIZE,
        "worker_running": _worker_task is not None and not _worker_task.done(),
    }


async def log_user_async(user_data: Dict[str, Any]) -> bool:
    return await enqueue_log("user", user_data)


async def log_session_async(session_data: Dict[str, Any]) -> bool:
    return await enqueue_log("session", session_data)


async def log_request_async(request_data: Dict[str, Any]) -> bool:
    return await enqueue_log("request", request_data)
