"""
Service Registry — centralized singleton instances.
All routers import from here to share cache, connection pools, etc.
"""
import logging
from app.services.netsuite_service import NetSuiteService
from app.services.production_service import ProductionService
from app.services.bom_service import BOMService
from app.services.inventory_service import InventoryService

logger = logging.getLogger(__name__)

# Shared NetSuite service (one HTTP client, one OAuth signer)
_netsuite_service = NetSuiteService()

# Production service with caching enabled
_production_service = ProductionService(
    netsuite_service=_netsuite_service,
    enable_cache=True,
    bom_ttl_seconds=3600,
    item_details_ttl_seconds=3600,
    inventory_ttl_seconds=300,
)

# BOM service sharing the same cache as production
_bom_service = BOMService(_netsuite_service, _production_service.cache_manager)

# Inventory service sharing the same NetSuite client
_inventory_service = InventoryService(_netsuite_service)

logger.info("Service registry initialized (shared NetSuite client + cache)")


def get_netsuite_service() -> NetSuiteService:
    return _netsuite_service


def get_production_service() -> ProductionService:
    return _production_service


def get_bom_service() -> BOMService:
    return _bom_service


def get_inventory_service() -> InventoryService:
    return _inventory_service
