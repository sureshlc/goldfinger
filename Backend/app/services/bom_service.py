"""
BOM Service with integrated caching support.
This version caches BOM fetches to avoid redundant NetSuite API calls.
"""
from typing import List, Dict, Optional
from app.services.netsuite_service import NetSuiteService
from app.utils.cache_manager import make_bom_cache_key, make_item_details_cache_key, make_bom_revision_cache_key
from app.utils.suiteql_sanitizer import validate_suiteql_identifier, sanitize_suiteql_value, validate_numeric_id
import logging
import time

logger = logging.getLogger(__name__)


class BOMService:
    def __init__(self, netsuite_service: NetSuiteService, cache_manager=None):
        self.netsuite_service = netsuite_service
        self.cache_manager = cache_manager

        if cache_manager:
            logger.info("BOMService initialized WITH caching")
        else:
            logger.info("BOMService initialized WITHOUT caching")

    async def get_item_id_by_sku(self, item_sku: str) -> Optional[str]:
        start_time = time.time()

        validate_suiteql_identifier(item_sku, "item_sku")
        safe_sku = sanitize_suiteql_value(item_sku)

        # A SKU can map to multiple items (e.g. an Assembly and an InvtPart share one itemid).
        # Prefer the Assembly so BOM/production resolution lands on the item that has a BOM;
        # SKUs that are only an InvtPart still resolve to that InvtPart (no Assembly match).
        sql = f"""
        SELECT id
        FROM item
        WHERE itemid = '{safe_sku}'
        AND isinactive = 'F'
        ORDER BY CASE WHEN itemtype = 'Assembly' THEN 0 ELSE 1 END, id
        """
        try:
            logger.debug(f"[BOM] Executing query: {sql}")
            result = await self.netsuite_service.execute_suiteql(sql)
            items = result.get('items', [])

            logger.debug(f"[BOM] Query returned {len(items)} results")
            if items:
                logger.debug(f"[BOM] Found item ID: {items[0]['id']}")

            elapsed = time.time() - start_time
            logger.info(f"[TIMING] get_item_id_by_sku for {item_sku} took {elapsed:.3f}s")

            if items:
                return items[0]["id"]
            return None
        except Exception as e:
            logger.error(f"Failed to get internal ID for SKU {item_sku}: {e}")
            return None

    async def get_item_bom(self, item_id: str) -> List[Dict]:
        """Fetch BOM components for an assembly item ID (legacy-first, native fallback).

        Legacy path: the custrecord_blend_bom_assembly join (~0.4s SuiteQL, NO REST). Covers the
        ~989 Blend BOMs that still populate that custom field — the vast majority today.

        Native fallback: only when legacy returns nothing (the handful of native NetSuite BOMs,
        e.g. flat/masterDefault BOMs whose custom field is empty). Resolves the item's masterDefault
        BOM -> current revision via the REST record API, then reads that revision's components.

        Order rationale: during the Blend->native migration almost every item is still legacy, so
        legacy-first avoids the ~1.2s REST call on ~99% of requests. Revisit toward native-first
        (and native optimization) post-migration.
        """
        validate_numeric_id(item_id, "item_id")

        # 1) Legacy path — fast SuiteQL custom-field join, no REST.
        components = await self._get_item_bom_legacy(item_id)
        if components:
            return components

        # 2) Native fallback — masterDefault revision via REST, then its components.
        revision_id = await self._resolve_current_revision(item_id)
        if revision_id:
            return await self._get_components_by_revision(revision_id)

        return []

    async def _resolve_current_revision(self, item_id: str) -> Optional[str]:
        """Resolve an assembly item's masterDefault BOM -> current revision id via the REST record API.

        Returns the bomRevision internal id, or None if the item has no assigned BOM / isn't an
        assembly / the record fetch fails (any of which triggers the legacy fallback).

        Cached by item_id (1h): the REST call is ~1.2s, so a feasibility load that walks the BOM
        via multiple passes only pays it once. Negatives are cached too (empty string) so legacy /
        non-assembly items don't re-fetch on every request before falling back.
        """
        validate_numeric_id(item_id, "item_id")

        rev_key = make_bom_revision_cache_key(item_id)
        if self.cache_manager:
            cached = await self.cache_manager.get(rev_key)
            if cached is not None:
                logger.debug(f"[BOM] Revision cache HIT for item {item_id}: '{cached}'")
                return cached or None  # "" is a cached negative (no native BOM)

        try:
            record = await self.netsuite_service.get_record(
                f"assemblyItem/{item_id}?expandSubResources=true"
            )
        except Exception as e:
            logger.warning(f"[BOM] REST record fetch failed for assemblyItem/{item_id}: {e}")
            return None  # transient failure: don't cache, let the fallback run and retry next time

        revision = None
        if record:
            boms = ((record.get("billOfMaterials") or {}).get("items")) or []
            if boms:
                chosen = next((b for b in boms if b.get("masterDefault")), boms[0])
                rev = (chosen.get("currentRevision") or {}).get("id")
                revision = str(rev) if rev else None

        if self.cache_manager:
            await self.cache_manager.set(rev_key, revision or "")

        if revision:
            logger.info(f"[BOM] Native resolution: item {item_id} -> bomRevision {revision}")
        return revision

    async def _get_components_by_revision(self, revision_id: str) -> List[Dict]:
        """Fetch BOM component lines for a specific bomRevision id (native path).

        Same projection as the legacy query, keyed on the revision instead of the custom-field
        assembly join, so downstream output shape is identical.
        """
        start_time = time.time()
        validate_numeric_id(revision_id, "revision_id")

        sql = f"""
        SELECT
            b.id AS bom_id,
            b.name AS bom_name,
            item.id as internal_id,
            item.itemid as component_sku,
            (CASE WHEN item.displayname IS NULL THEN item.description ELSE item.displayname END) AS component_displayname,
            item.displayname,
            item.description AS component_name,
            ROUND(component.quantity, 5) as quantity_required,
            COALESCE(iu.name, BUILTIN.DF(component.units)) as unit,
            CASE WHEN item.itemtype IN ('Assembly', 'Kit') THEN 'true' ELSE 'false' END as is_manufacturing,
            CASE WHEN item.isphantom = 'T' THEN 'true' ELSE 'false' END as is_phantom
        FROM bomRevisionComponentMember AS component
        JOIN bomRevision AS rev ON component.bomRevision = rev.id
        JOIN bom as b ON rev.billofmaterials = b.id
        JOIN item ON component.item = item.id
        LEFT JOIN ItemUnit as iu ON component.units = iu.key
        WHERE rev.id = '{revision_id}'
        AND item.id != 5837
        ORDER BY b.id
        """
        try:
            result = await self.netsuite_service.execute_suiteql(sql)
            items = result.get('items', [])

            elapsed = time.time() - start_time
            logger.info(
                f"[TIMING] _get_components_by_revision for revision {revision_id} took "
                f"{elapsed:.3f}s, returned {len(items)} components"
            )
            return items
        except Exception as e:
            logger.error(f"Failed to fetch components for revision {revision_id}: {e}")
            return []

    async def _get_item_bom_legacy(self, item_id: str) -> List[Dict]:
        """Legacy Blend BOM resolution via the custrecord_blend_bom_assembly custom field.

        Kept as a fallback during the Blend -> native migration. Once all BOMs are native this
        never returns rows (the custom field is empty on native BOMs) and can be removed.
        """
        start_time = time.time()
        validate_numeric_id(item_id, "item_id")

        sql = f"""
        SELECT
            b.id AS bom_id,
            b.name AS bom_name,
            item.id as internal_id,
            item.itemid as component_sku,
            (CASE WHEN item.displayname IS NULL THEN item.description ELSE item.displayname END) AS component_displayname,
            item.displayname,
            item.description AS component_name,
            ROUND(component.quantity, 5) as quantity_required,
            COALESCE(iu.name, BUILTIN.DF(component.units)) as unit,
            CASE WHEN item.itemtype IN ('Assembly', 'Kit') THEN 'true' ELSE 'false' END as is_manufacturing,
            CASE WHEN item.isphantom = 'T' THEN 'true' ELSE 'false' END as is_phantom
        FROM bomRevisionComponentMember AS component
        JOIN bomRevision AS rev ON component.bomRevision = rev.id
        JOIN bom as b ON rev.billofmaterials = b.id
        JOIN item ON component.item = item.id
        JOIN item parent_item ON b.custrecord_blend_bom_assembly = parent_item.id
        LEFT JOIN ItemUnit as iu ON component.units = iu.key
        WHERE parent_item.id = '{item_id}'
        AND item.id != 5837
        AND rev.isInactive = 'F'
        AND (rev.effectiveenddate IS NULL OR rev.effectiveenddate >= CURRENT_DATE)
        AND (rev.effectivestartdate IS NULL OR rev.effectivestartdate <= CURRENT_DATE)
        ORDER BY b.id
        """
        try:
            result = await self.netsuite_service.execute_suiteql(sql)
            items = result.get('items', [])

            elapsed = time.time() - start_time
            logger.info(f"[TIMING] _get_item_bom_legacy for item {item_id} took {elapsed:.3f}s, returned {len(items)} components")

            return items
        except Exception as e:
            logger.error(f"Failed to fetch legacy BOM for item {item_id}: {e}")
            return []

    async def get_item_details(self, item_id: str) -> Optional[Dict]:
        """Get detailed information for a specific item by ID. Uses cache if available."""
        # Check cache first
        if self.cache_manager:
            cache_key = make_item_details_cache_key(item_id)
            cached_details = await self.cache_manager.get(cache_key)
            if cached_details is not None:
                logger.debug(f"Cache HIT for item details: {item_id}")
                return cached_details

        start_time = time.time()
        validate_numeric_id(item_id, "item_id")

        sql = f"""
        SELECT
            id,
            itemid,
            COALESCE(description, itemid) as displayname,
            itemtype,
            description,
            CASE WHEN itemtype IN ('Assembly', 'Kit') THEN 'true' ELSE 'false' END as is_manufacturing
        FROM item
        WHERE id = '{item_id}'
        AND isinactive = 'F'
        """
        try:
            result = await self.netsuite_service.execute_suiteql(sql)
            items = result.get('items', [])

            elapsed = time.time() - start_time
            logger.info(f"[TIMING] get_item_details for {item_id} took {elapsed:.3f}s")

            item_details = items[0] if items else None

            # Cache the result
            if self.cache_manager and item_details:
                cache_key = make_item_details_cache_key(item_id)
                await self.cache_manager.set(cache_key, item_details)
                logger.debug(f"Cached item details for: {item_id}")

            return item_details
        except Exception as e:
            logger.error(f"Failed to get item details for item ID {item_id}: {e}")
            return None

    async def get_full_bom(self, item_sku: str, max_depth=5, current_depth=0) -> List[Dict]:
        """Recursively fetch the full multi-level BOM for an item by SKU, up to max_depth levels."""
        start_time = time.time()
        logger.info(f"[TIMING] get_full_bom called for SKU: {item_sku}, depth: {current_depth}")

        # Check cache at ALL depths
        if self.cache_manager:
            cache_key = make_bom_cache_key(item_sku)
            cached_bom = await self.cache_manager.get(cache_key)
            if cached_bom is not None:
                adjusted_bom = []
                for comp in cached_bom:
                    adjusted_comp = comp.copy()
                    adjusted_comp["level"] = comp.get("level", 0) + current_depth
                    adjusted_bom.append(adjusted_comp)

                elapsed = time.time() - start_time
                logger.info(f"[CACHE HIT] get_full_bom for {item_sku} at depth {current_depth} returned from cache in {elapsed:.3f}s, {len(adjusted_bom)} components")
                return adjusted_bom

        if current_depth > max_depth:
            return []

        item_id = await self.get_item_id_by_sku(item_sku)
        if not item_id:
            return []

        components = await self.get_item_bom(item_id)
        full_bom = []

        for component in components:
            component["level"] = current_depth
            full_bom.append(component)

            if component.get("is_manufacturing") == "true":
                sub_bom = await self.get_full_bom(
                    component["component_sku"],
                    max_depth,
                    current_depth + 1
                )
                full_bom.extend(sub_bom)

        elapsed = time.time() - start_time
        logger.info(f"[TIMING] get_full_bom for {item_sku} at depth {current_depth} took {elapsed:.3f}s, returned {len(full_bom)} total components")

        # Cache the result with base levels
        if self.cache_manager and full_bom:
            base_bom = []
            for comp in full_bom:
                base_comp = comp.copy()
                base_comp["level"] = comp.get("level", current_depth) - current_depth
                base_bom.append(base_comp)

            cache_key = make_bom_cache_key(item_sku)
            await self.cache_manager.set(cache_key, base_bom)
            logger.info(f"[CACHED] Full BOM for {item_sku} at depth {current_depth} cached with {len(base_bom)} components")

        return full_bom

    async def get_item_by_sku(self, item_sku: str) -> Optional[Dict]:
        """Get item details by SKU (used by production_service)."""
        item_id = await self.get_item_id_by_sku(item_sku)
        if not item_id:
            return None
        return await self.get_item_details(item_id)
