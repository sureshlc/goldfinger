"""
Main FastAPI Application with PostgreSQL + Integrated Logging System
"""
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.config import settings, validate_settings
from app.utils.local_sku_resolver import get_local_resolver
import logging
import sys

from app.dependencies.auth import get_current_user, get_admin_user
from app.database.connection import init_db, close_db

# Import logging components
from app.utils.csv_logger import get_csv_logger
from app.services.session_service import init_session_service, get_session_service
from app.background.db_writer import init_log_queue, start_db_writer, stop_db_writer
from app.middleware.logging_middleware import RequestLoggingMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

def setup_logging():
    log_level = getattr(logging, settings.log_level.upper())
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    if settings.environment == "production":
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)

    return logging.getLogger(__name__)

logger = setup_logging()

# ============================================================================
# APPLICATION LIFECYCLE
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        validate_settings()

        if settings.environment == "development":
            logger.info(f"Starting {settings.app_name}...")
        else:
            logger.info(f"{settings.app_name} starting in {settings.environment} mode")

        # Initialize database
        logger.info("Initializing database connection...")
        await init_db()
        logger.info("Database connection established")

        # Initialize CSV logger (DB-backed now)
        get_csv_logger()
        logger.info("Logger initialized")

        # Initialize session service
        init_session_service(session_timeout_minutes=30)
        logger.info("Session service initialized")

        # Initialize and start background DB writer
        init_log_queue()
        await start_db_writer()
        logger.info("Background DB writer started")

        # Load local SKU resolver from database
        resolver = get_local_resolver()
        await resolver.load_from_db()
        logger.info("Local SKU resolver loaded from database")

        logger.info("All systems initialized successfully")

        yield

    finally:
        logger.info("Application shutting down")

        await stop_db_writer()
        logger.info("Background DB writer stopped")

        session_service = get_session_service()
        session_service.shutdown()
        logger.info("Session service shut down")

        await close_db()
        logger.info("Database connection closed")

        logger.info("Shutdown complete")

# ============================================================================
# APPLICATION SETUP
# ============================================================================

app = FastAPI(
    title=settings.app_name,
    description="Production Agent API for inventory management and BOM analysis",
    version=settings.api_version,
    debug=settings.debug,
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url="/redoc" if settings.environment != "production" else None,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

# Add Security Headers middleware
app.add_middleware(SecurityHeadersMiddleware)

# Add Request Logging middleware
app.add_middleware(RequestLoggingMiddleware)

# Include routers
try:
    from app.routers import items, inventory, production, auth, admin, analytics

    app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
    app.include_router(items.router, prefix=f"/api/{settings.api_version}/items", tags=["Items"])
    app.include_router(inventory.router, prefix=f"/api/{settings.api_version}/inventory", tags=["Inventory"])
    app.include_router(production.router, prefix=f"/api/{settings.api_version}/production", tags=["Production"])
    app.include_router(admin.router, prefix="/api/v1/admin", tags=["Admin"])
    app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["Analytics"])

    logger.info("All routers loaded")
except ImportError as e:
    logger.warning(f"Some routers not found: {e}")

# ============================================================================
# HEALTH & ADMIN ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    return {
        "message": f"Welcome to {settings.app_name}",
        "version": settings.api_version,
        "environment": settings.environment,
        "status": "healthy",
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": settings.api_version,
        "environment": settings.environment,
    }

@app.get("/admin/logging-stats")
async def logging_stats(current_user=Depends(get_admin_user)):
    from app.background.db_writer import get_queue_stats
    from app.database.connection import get_session_factory
    from app.database.repositories.log_repo import get_log_stats

    session_service = get_session_service()
    session_stats = session_service.get_stats()
    queue_stats = await get_queue_stats()

    try:
        factory = get_session_factory()
        async with factory() as session:
            db_stats = await get_log_stats(session)
    except Exception:
        db_stats = {}

    return {
        "database_logging": db_stats,
        "sessions": session_stats,
        "queue": queue_stats,
        "log_level": settings.log_level,
        "environment": settings.environment,
    }

@app.post("/admin/reload-items")
async def reload_items(current_user=Depends(get_admin_user)):
    try:
        resolver = get_local_resolver()
        await resolver.reload()
        logger.info("Items reloaded from database via admin endpoint")
        return {"status": "success", "message": "Items reloaded successfully"}
    except Exception as e:
        logger.error(f"Failed to reload items: {e}")
        return {"status": "error", "message": "Failed to reload items"}

# ============================================================================
# APPLICATION ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
        access_log=settings.environment == "development",
    )
