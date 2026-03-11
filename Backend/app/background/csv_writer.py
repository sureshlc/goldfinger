"""
Background CSV Writer Service
Handles async batch writing of logs to CSV files using AsyncIO queue.

Save as: app/background/csv_writer.py
"""
import asyncio
from typing import Dict, Any, Optional
import logging
from datetime import datetime

from app.utils.csv_logger import get_csv_logger

logger = logging.getLogger(__name__)

# Global queue for log events
log_queue: Optional[asyncio.Queue] = None

# Background worker task reference
_worker_task: Optional[asyncio.Task] = None

# Batch configuration
BATCH_SIZE = 50  # Write after 50 requests
BATCH_TIMEOUT = 5.0  # Or write after 5 seconds
QUEUE_MAX_SIZE = 10000  # Prevent memory overflow


class LogEvent:
    """Represents a log event to be written"""
    
    def __init__(self, event_type: str, data: Dict[str, Any]):
        """
        Initialize log event
        
        Args:
            event_type: Type of event ('user', 'session', 'request')
            data: Event data dictionary
        """
        self.event_type = event_type
        self.data = data
        self.timestamp = datetime.utcnow()


def init_log_queue():
    """Initialize the global log queue"""
    global log_queue
    if log_queue is None:
        log_queue = asyncio.Queue(maxsize=QUEUE_MAX_SIZE)
        logger.info(f"Log queue initialized (max_size={QUEUE_MAX_SIZE})")


async def enqueue_log(event_type: str, data: Dict[str, Any]) -> bool:
    """
    Add log event to queue (non-blocking)
    
    Args:
        event_type: Type of event ('user', 'session', 'request')
        data: Event data dictionary
        
    Returns:
        bool: True if enqueued, False if queue is full
    """
    global log_queue
    
    if log_queue is None:
        logger.warning("Log queue not initialized, initializing now")
        init_log_queue()
    
    try:
        event = LogEvent(event_type, data)
        # Use put_nowait to avoid blocking the request
        log_queue.put_nowait(event)
        return True
    except asyncio.QueueFull:
        logger.error(f"Log queue full! Dropping {event_type} event")
        return False
    except Exception as e:
        logger.error(f"Failed to enqueue log: {e}")
        return False


async def csv_writer_worker():
    """
    Background worker that processes log queue and writes to CSV
    Batches writes for efficiency
    """
    global log_queue
    csv_logger = get_csv_logger()
    
    logger.info("CSV writer worker started")
    
    # Batch buffers
    request_batch = []
    
    try:
        while True:
            try:
                # Wait for events with timeout for batch processing
                # Use shorter timeout to be more responsive to cancellation
                event = await asyncio.wait_for(
                    log_queue.get(),
                    timeout=1.0  # Reduced from BATCH_TIMEOUT for faster shutdown
                )
                
                # Process event based on type
                if event.event_type == "user":
                    # Write user events immediately (low volume)
                    csv_logger.append_user(event.data)
                    
                elif event.event_type == "session":
                    # Write session events immediately (low volume)
                    csv_logger.append_session(event.data)
                    
                elif event.event_type == "request":
                    # Batch request events (high volume)
                    request_batch.append(event.data)
                    
                    # Write batch if size threshold reached
                    if len(request_batch) >= BATCH_SIZE:
                        count = csv_logger.batch_append_requests(request_batch)
                        logger.debug(f"Wrote batch of {count} requests")
                        request_batch.clear()
                
                # Mark task as done
                log_queue.task_done()
                
            except asyncio.TimeoutError:
                # Timeout reached, write any pending batches
                if request_batch:
                    count = csv_logger.batch_append_requests(request_batch)
                    logger.debug(f"Wrote timeout batch of {count} requests")
                    request_batch.clear()
                # Continue loop to check for cancellation
                continue
                
            except Exception as e:
                logger.error(f"Error processing log event: {e}")
                # Continue processing other events
                
    except asyncio.CancelledError:
        # Worker is being shut down
        logger.info("CSV writer worker shutting down...")
        
        # Flush any remaining batches
        if request_batch:
            count = csv_logger.batch_append_requests(request_batch)
            logger.info(f"Flushed final batch of {count} requests")
        
        # Process remaining items in queue (with limit to prevent hanging)
        remaining = 0
        max_flush = 100  # Limit how many we process during shutdown
        
        while not log_queue.empty() and remaining < max_flush:
            try:
                event = log_queue.get_nowait()
                
                if event.event_type == "user":
                    csv_logger.append_user(event.data)
                elif event.event_type == "session":
                    csv_logger.append_session(event.data)
                elif event.event_type == "request":
                    csv_logger.append_request(event.data)
                
                log_queue.task_done()
                remaining += 1
            except asyncio.QueueEmpty:
                break
            except Exception as e:
                logger.error(f"Error flushing event during shutdown: {e}")
                break
        
        if remaining > 0:
            logger.info(f"Flushed {remaining} remaining log events")
        
        if not log_queue.empty():
            logger.warning(f"Queue still has {log_queue.qsize()} items after shutdown")
        
        logger.info("CSV writer worker stopped")
        raise


async def start_csv_writer():
    """Start the background CSV writer worker"""
    global _worker_task, log_queue
    
    if _worker_task is not None:
        logger.warning("CSV writer worker already running")
        return
    
    # Initialize queue if not already done
    if log_queue is None:
        init_log_queue()
    
    # Start background worker
    _worker_task = asyncio.create_task(csv_writer_worker())
    logger.info("CSV writer background task started")


async def stop_csv_writer(timeout: float = 5.0):
    """
    Stop the background CSV writer worker and flush queue
    
    Args:
        timeout: Maximum time to wait for graceful shutdown
    """
    global _worker_task, log_queue
    
    if _worker_task is None:
        logger.warning("CSV writer worker not running")
        return
    
    logger.info("Stopping CSV writer worker...")
    
    # Cancel the worker task
    _worker_task.cancel()
    
    try:
        # Wait for worker to finish cleanup with timeout
        await asyncio.wait_for(_worker_task, timeout=timeout)
    except asyncio.CancelledError:
        logger.info("Worker cancelled successfully")
    except asyncio.TimeoutError:
        logger.warning(f"Worker shutdown timed out after {timeout}s")
    except Exception as e:
        logger.error(f"Error during worker shutdown: {e}")
    
    _worker_task = None
    logger.info("CSV writer worker stopped successfully")


async def get_queue_stats() -> Dict[str, Any]:
    """Get statistics about the log queue"""
    global log_queue
    
    if log_queue is None:
        return {
            "queue_initialized": False,
            "queue_size": 0,
            "queue_max_size": 0
        }
    
    return {
        "queue_initialized": True,
        "queue_size": log_queue.qsize(),
        "queue_max_size": QUEUE_MAX_SIZE,
        "worker_running": _worker_task is not None and not _worker_task.done()
    }


# Convenience functions for logging
async def log_user_async(user_data: Dict[str, Any]) -> bool:
    """Async convenience function to log user data"""
    return await enqueue_log("user", user_data)


async def log_session_async(session_data: Dict[str, Any]) -> bool:
    """Async convenience function to log session data"""
    return await enqueue_log("session", session_data)


async def log_request_async(request_data: Dict[str, Any]) -> bool:
    """Async convenience function to log request data"""
    return await enqueue_log("request", request_data)