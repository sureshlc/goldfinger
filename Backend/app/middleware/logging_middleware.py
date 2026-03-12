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
            
            # Extract request data
            log_data = await self._extract_request_data(
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
    ) -> dict:
        """
        Extract relevant data from request for logging
        
        Args:
            request: FastAPI request object
            request_id: Generated request ID
            session_id: Session ID if available
            user_id: User ID if available
            response_time_ms: Response time in milliseconds
            status_code: HTTP status code
            error_type: Error type if any
            error_message: Error message if any
            response: Response object
            
        Returns:
            Dict with request data for CSV logging
        """
        # Base data
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "request_id": request_id,
            "session_id": session_id or "",
            "user_id": user_id or "",
            "response_time_ms": response_time_ms,
            "status_code": status_code,
            "error_type": error_type or "",
            "error_message": error_message or "",
            "location": ""  # Not capturing location/IP data
        }
        
        # Extract business logic data based on endpoint
        if "/api/v1/production/" in request.url.path:
            await self._extract_production_check_data(request, response, log_data)
        else:
            # For non-production endpoints, set empty values
            log_data["item_sku"] = ""
            log_data["desired_quantity"] = ""
            log_data["max_producible"] = ""
            log_data["can_produce"] = ""
            log_data["limiting_component"] = ""
            log_data["shortages_count"] = ""
        
        # Check if response was from cache
        if response and hasattr(response, "headers"):
            log_data["cache_hit"] = response.headers.get("X-Cache-Hit", "false")
        else:
            log_data["cache_hit"] = ""
        
        return log_data
    
    async def _extract_production_check_data(
        self, 
        request: Request, 
        response: Optional[Response], 
        log_data: dict
    ) -> None:
        """
        Extract production-specific data from request state
        
        Args:
            request: FastAPI request object
            response: Response object (unused but kept for consistency)
            log_data: Dict to populate with production data
        """
        try:
            if hasattr(request.state, "production_data"):
                prod_data = request.state.production_data
                log_data["item_sku"] = prod_data.get("item_sku", "")
                log_data["desired_quantity"] = prod_data.get("desired_quantity", "")
                log_data["max_producible"] = prod_data.get("max_producible", "")
                log_data["can_produce"] = prod_data.get("can_produce", "")
                log_data["limiting_component"] = prod_data.get("limiting_component", "")
                log_data["shortages_count"] = prod_data.get("shortages_count", "")
                logger.debug(f"✅ Extracted production data: {prod_data}")
            else:
                # Set empty values if no production data
                log_data["item_sku"] = ""
                log_data["desired_quantity"] = ""
                log_data["max_producible"] = ""
                log_data["can_produce"] = ""
                log_data["limiting_component"] = ""
                log_data["shortages_count"] = ""
                logger.debug("⚠️ No production_data found in request.state")
        except Exception as e:
            logger.error(f"Error extracting production data: {e}")
            # Set empty values on error
            log_data["item_sku"] = ""
            log_data["desired_quantity"] = ""
            log_data["max_producible"] = ""
            log_data["can_produce"] = ""
            log_data["limiting_component"] = ""
            log_data["shortages_count"] = ""
    
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