"""
Logging Middleware for Request Tracking
Captures all API requests and logs them to CSV via background queue.

Save as: app/middleware/logging_middleware.py
"""
import time
from datetime import datetime
from typing import Callable, Optional
import logging
from threading import RLock

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.background.db_writer import log_request_async
from app.services.session_service import get_session_service

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to log all API requests to CSV
    Captures request/response data and pushes to async queue
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        # Don't store session_service - get it fresh on each request
        self._request_counter = 0
        self._lock = RLock()  # Thread-safe counter
    
    def _generate_request_id(self) -> str:
        """Generate sequential request ID"""
        with self._lock:
            self._request_counter += 1
            return str(self._request_counter)
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and log data
        
        Args:
            request: FastAPI request object
            call_next: Next middleware/handler in chain
            
        Returns:
            Response object
        """
        # Skip logging for certain endpoints
        if self._should_skip_logging(request):
            return await call_next(request)
        
        # Generate sequential request ID
        request_id = self._generate_request_id()
        
        # Capture start time
        start_time = time.time()
        
        # Initialize variables (will extract user/session info later, after dependencies run)
        user_id = None
        session_id = None
        
        # Initialize response variables
        response = None
        status_code = 500
        error_type = None
        error_message = None
        
        try:
            # Call next middleware/handler
            response = await call_next(request)
            status_code = response.status_code
            
            # Check if response indicates an error
            if status_code >= 400:
                error_type = self._get_error_type(status_code)
                
        except Exception as e:
            # Capture exception details
            error_type = type(e).__name__
            error_message = str(e)
            logger.error(f"Request {request_id} failed: {error_type} - {error_message}")
            raise  # Re-raise to let FastAPI handle it
            
        finally:
            # NOW extract user and session info (after dependencies have run)
            try:
                if hasattr(request.state, "user"):
                    user = request.state.user
                    user_id = str(user.id)
                    logger.debug(f"Middleware captured user_id: {user_id}")
                    
                    # Get session service (fresh instance per request)
                    session_service = get_session_service()
                    
                    logger.debug(f"Looking for session with user_id: '{user_id}' (type: {type(user_id)})")
                    logger.debug(f"Available user_sessions: {session_service.user_sessions}")
                    
                    # Get active session for user
                    session = session_service.get_user_session(user_id)
                    if session:
                        session_id = session.session_id
                        logger.debug(f"Found session_id: {session_id}")
                        # Increment request count for session
                        session_service.increment_request_count(session_id)
                    else:
                        logger.warning(f"No session found for user_id: {user_id}")
                else:
                    logger.debug("request.state.user not found")
            except Exception as e:
                logger.error(f"Exception getting user: {e}", exc_info=True)
            
            # Calculate response time
            response_time_ms = round((time.time() - start_time) * 1000, 2)
            
            # Extract request data — a list of one row per logged record
            # (multi-SKU batch requests produce one row per SKU)
            log_rows = await self._extract_request_data(
                request=request,
                request_id=request_id,
                session_id=session_id,
                user_id=user_id,
                response_time_ms=response_time_ms,
                status_code=status_code,
                error_type=error_type,
                error_message=error_message,
                response=response
            )

            # Push to async queue (non-blocking)
            for log_data in log_rows:
                try:
                    logger.debug(f"About to enqueue log_data: {log_data}")
                    await log_request_async(log_data)
                except Exception as e:
                    logger.error(f"Failed to enqueue log for request {request_id}: {e}")
        
        return response
    
    def _should_skip_logging(self, request: Request) -> bool:
        """
        Determine if request should skip logging
        
        Args:
            request: FastAPI request object
            
        Returns:
            bool: True if should skip logging
        """
        # Skip OPTIONS requests (CORS preflight)
        if request.method == "OPTIONS":
            return True
        
        # Only log production feasibility checks — skip everything else
        path = request.url.path
        if "/api/v1/production/" in path:
            return False
        return True
    
    async def _extract_request_data(
        self,
        request: Request,
        request_id: str,
        session_id: Optional[str],
        user_id: Optional[str],
        response_time_ms: float,
        status_code: int,
        error_type: Optional[str],
        error_message: Optional[str],
        response: Optional[Response]
    ) -> list:
        """
        Build the request log row(s) for a request.

        Returns a list of dicts — one row per logged record. A single-SKU request
        produces one row; a multi-SKU batch (production_data is a list) produces one
        row per SKU, all sharing the same request_id.
        """
        # Base data shared by every row for this request
        base = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "request_id": request_id,
            "session_id": session_id or "",
            "user_id": user_id or "",
            "response_time_ms": response_time_ms,
            "status_code": status_code,
            "error_type": error_type or "",
            "error_message": error_message or "",
            "location": "",  # Not capturing location/IP data
            "source": self._get_source(request),
        }

        # Check if response was from cache
        if response and hasattr(response, "headers"):
            base["cache_hit"] = response.headers.get("X-Cache-Hit", "false")
        else:
            base["cache_hit"] = ""

        # Production endpoints carry SKU-level data; everything else logs one bare row.
        if "/api/v1/production/" in request.url.path:
            prod = getattr(request.state, "production_data", None)
            if isinstance(prod, list):
                rows = [{**base, **self._prod_fields(entry)} for entry in prod]
                if rows:
                    logger.debug(f"✅ Extracted {len(rows)} multi-SKU production rows")
                    return rows
            elif isinstance(prod, dict):
                logger.debug(f"✅ Extracted production data: {prod}")
                return [{**base, **self._prod_fields(prod)}]
            else:
                logger.debug("⚠️ No production_data found in request.state")

        return [{**base, **self._empty_prod()}]

    @staticmethod
    def _get_source(request: Request) -> str:
        """Map the auth method to a source tag: 'REST' for API-key/MES, else 'UI'."""
        auth_method = getattr(request.state, "auth_method", None)
        return "REST" if auth_method == "api_key" else "UI"

    @staticmethod
    def _prod_fields(data: dict) -> dict:
        """Normalize one SKU's production fields for a log row."""
        return {
            "item_sku": data.get("item_sku") or "",
            "desired_quantity": data.get("desired_quantity") or "",
            "max_producible": data.get("max_producible") or "",
            "can_produce": data.get("can_produce") or "",
            "limiting_component": data.get("limiting_component") or "",
            "shortages_count": data.get("shortages_count") or "",
        }

    @staticmethod
    def _empty_prod() -> dict:
        return {
            "item_sku": "",
            "desired_quantity": "",
            "max_producible": "",
            "can_produce": "",
            "limiting_component": "",
            "shortages_count": "",
        }
    
    def _get_error_type(self, status_code: int) -> str:
        """
        Get error type from status code
        
        Args:
            status_code: HTTP status code
            
        Returns:
            str: Error type description
        """
        error_types = {
            400: "BadRequest",
            401: "Unauthorized",
            403: "Forbidden",
            404: "NotFound",
            422: "ValidationError",
            500: "InternalServerError",
            502: "BadGateway",
            503: "ServiceUnavailable"
        }
        
        return error_types.get(status_code, f"HTTPError{status_code}")