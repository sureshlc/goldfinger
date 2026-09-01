"""
BOM Service with integrated caching support.
This version caches BOM fetches to avoid redundant NetSuite API calls.
"""
from typing import List, Dict, Optional
from app.services.netsuite_service import NetSuiteService
from app.utils.cache_manager import make_bom_cache_key, make_item_details_cache_key, make_bom_revision_cache_key
from app.utils.suiteql_sanitizer import validate_suiteql_identifier, sanitize_suiteql_value, validate_numeric_id
import asyncio
import logging
import os
import time

logger = logging.getLogger(__name__)

# Persisted BOM cache (Postgres read-through). Kill-switch + safety re-fetch window, env-overridable.
BOM_DB_CACHE_ENABLED = os.getenv("BOM_DB_CACHE_ENABLED", "true").strip().lower() != "false"
try:
    BOM_CACHE_MAX_AGE_DAYS = int(os.getenv("BOM_CACHE_MAX_AGE_DAYS", "14"))
except ValueError:
    BOM_CACHE_MAX_AGE_DAYS = 14

# Cross-process mutex for "refresh all formulas": the live app (admin button) and the
# standalone weekly cron script run in different processes, so an in-memory guard can't
# serialize them. A fixed-key Postgres session-level advisory lock does. Arbitrary but
# stable 64-bit key; must not collide with any other advisory lock in this DB.
BOM_REFRESH_LOCK_KEY = 4200079

# Progress of a "refresh all formulas" run (admin trigger or weekly cron). Single run at a time.
_refresh_status = {
    "running": False, "total": 0, "done": 0, "errors": 0,
    "started_at": None, "finished_at": None, "last_summary": None,
}
_refresh_tasks: set = set()  # hold background task refs so they aren't GC'd


def get_bom_refresh_status() -> dict:
    return dict(_refresh_status)


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
        """Fetch an assembly's direct BOM components. Read-through: Postgres cache -> NetSuite.

        Lookup order: persisted bom_formula/bom_component cache (no NetSuite) -> NetSuite resolution
        (legacy-first, native fallback) which is then written back to the cache. Callers and the
        full-tree recursion are unchanged; each level is just served from the DB on a cache hit.
        """
        validate_numeric_id(item_id, "item_id")

        # L2: persisted formula cache (no NetSuite call on a hit).
        cached = await self._read_bom_from_db(item_id)
        if cached is not None:
            return cached

        # L3: resolve from NetSuite, then write back to the cache — but only if resolution
        # succeeded. A NetSuite error (e.g. 429) must NOT overwrite a good cached formula.
        components, source, revision_id, has_bom, ok = await self._resolve_bom_from_netsuite(item_id)
        if ok:
            await self._write_bom_to_db(item_id, components, source, revision_id, has_bom)
            return components

        # Resolution failed — fall back to a stale cached formula if we have one, else empty.
        stale = await self._read_bom_from_db(item_id, allow_stale=True)
        return stale if stale is not None else components

    async def _resolve_bom_from_netsuite(self, item_id: str):
        """Resolve an assembly's direct BOM from NetSuite (legacy-first, native fallback).

        Legacy path: the custrecord_blend_bom_assembly SuiteQL join (no REST) — covers the ~989
        Blend BOMs. Native fallback: masterDefault -> currentRevision via the REST record API for
        the handful of native BOMs.

        Returns (components, source, revision_id, has_bom, ok). `ok` is False when a NetSuite call
        ERRORED (429 exhausted, connection, etc.) — the empty result is then "unknown", not a
        confirmed "no BOM", so callers must NOT persist/overwrite the cache with it.
        """
        try:
            components = await self._get_item_bom_legacy(item_id)
            if components:
                return components, "legacy", None, True, True

            revision_id = await self._resolve_current_revision(item_id)
            if revision_id:
                components = await self._get_components_by_revision(revision_id)
                return components, "native", revision_id, bool(components), True

            return [], "native", None, False, True   # confirmed: item has no BOM
        except Exception as e:
            logger.warning(f"[BOM] NetSuite resolution failed for item {item_id}: {e}")
            return [], "unknown", None, False, False  # error -> don't clobber the cache

    @staticmethod
    def _component_row_to_dict(row) -> Dict:
        """Map a persisted bom_component row back to the component dict shape callers expect."""
        return {
            "bom_id": row.bom_id or "",
            "bom_name": "",
            "internal_id": str(row.component_item_id),
            "component_sku": row.component_sku,
            "component_displayname": row.component_name or "",
            "displayname": row.component_name or "",
            "component_name": row.component_name or "",
            "quantity_required": float(row.quantity),
            "unit": row.unit,
            "is_manufacturing": "true" if row.is_manufacturing else "false",
            "is_phantom": "true" if row.is_phantom else "false",
        }

    async def _read_bom_from_db(self, item_id: str, allow_stale: bool = False):
        """Return cached components (possibly empty for a negative cache), or None on a miss/stale/error.

        allow_stale=True ignores the max-age check — used as a fallback when a live re-fetch fails,
        so we serve slightly-old data rather than nothing.
        """
        if not BOM_DB_CACHE_ENABLED:
            return None
        try:
            from datetime import datetime, timezone, timedelta
            from app.database.connection import get_session_factory
            from app.database.repositories.bom_repo import get_bom_formula, get_bom_components

            factory = get_session_factory()
            async with factory() as session:
                formula = await get_bom_formula(session, int(item_id))
                if formula is None:
                    return None  # not cached -> miss

                # Safety re-fetch if the formula hasn't been refreshed in a long time.
                if not allow_stale and BOM_CACHE_MAX_AGE_DAYS and formula.refreshed_at is not None:
                    ref = formula.refreshed_at
                    if ref.tzinfo is None:
                        ref = ref.replace(tzinfo=timezone.utc)
                    if datetime.now(timezone.utc) - ref > timedelta(days=BOM_CACHE_MAX_AGE_DAYS):
                        return None  # stale -> re-fetch

                if not formula.has_bom:
                    return []  # negative cache: item has no BOM

                rows = await get_bom_components(session, int(item_id))
                return [self._component_row_to_dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"[BOM] DB cache read failed for item {item_id}: {e}")
            return None  # fall through to NetSuite

    async def _write_bom_to_db(self, item_id: str, components, source, revision_id, has_bom) -> None:
        """Persist a freshly-resolved formula + components (best effort; never blocks the response)."""
        if not BOM_DB_CACHE_ENABLED:
            return
        try:
            from app.database.connection import get_session_factory
            from app.database.repositories.bom_repo import upsert_bom_formula, replace_bom_components

            factory = get_session_factory()
            async with factory() as session:
                await upsert_bom_formula(session, int(item_id), revision_id, source, bool(has_bom))
                await replace_bom_components(session, int(item_id), components or [])
                await session.commit()
        except Exception as e:
            logger.warning(f"[BOM] DB cache write failed for item {item_id}: {e}")

    async def refresh_bom_formula(self, item_id: str) -> Dict:
        """Force a re-fetch of ONE assembly's direct BOM from NetSuite and overwrite the cache.
        Also drops the stale in-memory layers for that item."""
        validate_numeric_id(item_id, "item_id")
        components, source, revision_id, has_bom, ok = await self._resolve_bom_from_netsuite(item_id)
        if not ok:
            raise RuntimeError(f"NetSuite resolution failed for item {item_id}; kept existing formula")
        await self._write_bom_to_db(item_id, components, source, revision_id, has_bom)
        if self.cache_manager:
            await self.cache_manager.invalidate(make_bom_revision_cache_key(item_id))
            details = await self.get_item_details(item_id)
            sku = (details or {}).get("itemid")
            if sku:
                await self.cache_manager.invalidate(make_bom_cache_key(sku))
        logger.info(f"[BOM-refresh] item {item_id}: {len(components)} components ({source})")
        return {"item_id": str(item_id), "components": len(components), "has_bom": has_bom, "source": source}

    async def refresh_all_bom_formulas(self, pace_seconds: float = 0.4) -> Dict:
        """Re-fetch every cached assembly's direct BOM, paced to respect NetSuite limits.

        Reused by the manual admin trigger and the weekly cron. Because those run in
        DIFFERENT processes (live app vs. standalone cron script), the in-memory
        _refresh_status guard can't prevent them colliding — so we take a Postgres
        session-level advisory lock. Only one refresh proceeds regardless of trigger
        source; a second concurrent trigger returns immediately as skipped.

        Progress is tracked in the module-level _refresh_status (readable via
        get_bom_refresh_status)."""
        from datetime import datetime, timezone
        from sqlalchemy import text
        from app.database.connection import get_session_factory, get_engine
        from app.database.repositories.bom_repo import get_all_formula_ids

        # Dedicated connection held open for the whole run so the session-level
        # advisory lock persists until we explicitly unlock (survives txn boundaries).
        lock_conn = await get_engine().connect()
        try:
            got_lock = (
                await lock_conn.execute(
                    text("SELECT pg_try_advisory_lock(:k)"),
                    {"k": BOM_REFRESH_LOCK_KEY},
                )
            ).scalar()
            # Commit so the connection sits plain-idle, NOT idle-in-transaction, for the
            # multi-minute run. Session-level advisory locks survive the commit, so the
            # mutex holds — but we're now immune to idle_in_transaction_session_timeout
            # terminating the connection and silently releasing the lock.
            await lock_conn.commit()
            if not got_lock:
                logger.warning(
                    "[BOM-refresh] another refresh already holds the advisory lock; skipping"
                )
                skipped = {"skipped": True, "reason": "another refresh in progress"}
                _refresh_status.update({
                    "running": False,
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "last_summary": skipped,
                })
                return skipped

            factory = get_session_factory()
            async with factory() as session:
                ids = await get_all_formula_ids(session)

            start = time.time()
            _refresh_status.update({
                "running": True, "total": len(ids), "done": 0, "errors": 0,
                "started_at": datetime.now(timezone.utc).isoformat(), "finished_at": None,
            })
            logger.info(f"[BOM-refresh] starting full refresh of {len(ids)} formulas")

            refreshed, errors = 0, 0
            try:
                for i, iid in enumerate(ids):
                    try:
                        await self.refresh_bom_formula(str(iid))
                        refreshed += 1
                    except Exception as e:
                        errors += 1
                        logger.warning(f"[BOM-refresh] item {iid} failed: {e}")
                    _refresh_status.update({"done": i + 1, "errors": errors})
                    if pace_seconds:
                        await asyncio.sleep(pace_seconds)
            finally:
                summary = {
                    "total": len(ids), "refreshed": refreshed, "errors": errors,
                    "seconds": round(time.time() - start, 1),
                }
                _refresh_status.update({
                    "running": False,
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "last_summary": summary,
                })
                logger.info(f"[BOM-refresh] done: {summary}")
            return summary
        finally:
            try:
                await lock_conn.execute(
                    text("SELECT pg_advisory_unlock(:k)"), {"k": BOM_REFRESH_LOCK_KEY}
                )
                await lock_conn.commit()
            finally:
                await lock_conn.close()

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
            raise  # propagate so the resolver marks this a failure and doesn't clobber the cache

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
            raise

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
            raise

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

    async def get_full_bom(self, item_sku: str, max_depth=5, current_depth=0, item_id: Optional[str] = None) -> List[Dict]:
        """Recursively fetch the full multi-level BOM for an item by SKU, up to max_depth levels.

        item_id, when passed, is the already-known internal id for item_sku (carried down from the
        parent's component row) — it lets the recursion skip a redundant SKU->id NetSuite lookup.
        """
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

        # Use the id already carried in the parent's component row to skip a redundant SKU->id
        # NetSuite lookup; resolve from the SKU only at the top level (or as a defensive fallback).
        if not item_id:
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
                    current_depth + 1,
                    item_id=component.get("internal_id"),
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
