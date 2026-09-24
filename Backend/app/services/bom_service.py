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

    async def get_item_ids_by_skus_bulk(self, item_skus: List[str]) -> Dict[str, str]:
        """Resolve many SKUs -> internal id in ONE SuiteQL (WHERE itemid IN (...)).

        Bulk twin of get_item_id_by_sku with the same Assembly-preference: a SKU shared by an
        Assembly and an InvtPart resolves to the Assembly (the one that carries a BOM). Returns
        {sku: id} for SKUs that exist; unknown SKUs are simply absent. Used as the resolve_skus_bulk
        NetSuite fallback so a cold batch of brand-new SKUs resolves in one call, not one per SKU.
        """
        if not item_skus:
            return {}
        safe = []
        for sku in item_skus:
            validate_suiteql_identifier(sku, "item_sku")
            safe.append(sanitize_suiteql_value(sku))
        sku_list = ",".join(f"'{s}'" for s in safe)

        # ORDER BY itemid then Assembly-first so the first row per SKU is the preferred (Assembly) id.
        sql = f"""
        SELECT id, itemid, itemtype
        FROM item
        WHERE itemid IN ({sku_list})
        AND isinactive = 'F'
        ORDER BY itemid, CASE WHEN itemtype = 'Assembly' THEN 0 ELSE 1 END, id
        """
        start_time = time.time()
        result = await self.netsuite_service.execute_suiteql(sql)
        rows = result.get('items', [])
        out: Dict[str, str] = {}
        for row in rows:
            sku = str(row.get("itemid"))
            if sku not in out:  # first per SKU wins (Assembly-preferred via ORDER BY)
                out[sku] = str(row.get("id"))
        logger.info(
            f"[TIMING] get_item_ids_by_skus_bulk for {len(item_skus)} skus took "
            f"{time.time() - start_time:.3f}s, {len(out)} resolved"
        )
        return out

    async def get_item_bom(self, item_id: str) -> List[Dict]:
        """Fetch an assembly's direct BOM components (see _get_item_bom_with_source; source dropped)."""
        components, _ = await self._get_item_bom_with_source(item_id)
        return components

    async def _get_item_bom_with_source(self, item_id: str):
        """Fetch an assembly's direct BOM components AND its source ('native' | 'legacy' | ...).

        Read-through: persisted bom_formula/bom_component cache (no NetSuite) -> NetSuite resolution
        (native-first, legacy fallback) which is then written back to the cache. The source lets the
        full-tree walk pick per node: native BOMs are flat (stocked-leaf sub-assemblies), legacy
        BOMs expand multi-level as before. Returns (components, source).
        """
        validate_numeric_id(item_id, "item_id")

        # L2: persisted formula cache (no NetSuite call on a hit).
        cached = await self._read_bom_from_db(item_id)
        if cached is not None:
            return cached  # (components, source)

        # L3: resolve from NetSuite, then write back to the cache — but only if resolution
        # succeeded. A NetSuite error (e.g. 429) must NOT overwrite a good cached formula.
        components, source, revision_id, has_bom, ok = await self._resolve_bom_from_netsuite(item_id)
        if ok:
            await self._write_bom_to_db(item_id, components, source, revision_id, has_bom)
            return components, source

        # Resolution failed — fall back to a stale cached formula if we have one, else empty.
        stale = await self._read_bom_from_db(item_id, allow_stale=True)
        return stale if stale is not None else (components, source)

    async def _resolve_bom_from_netsuite(self, item_id: str):
        """Resolve an assembly's direct BOM from NetSuite (native-first, legacy fallback).

        Native path (primary): assemblyItemBom.currentrevision -> components, ALL in SuiteQL (no
        REST record call), so a single query shape also batches many assemblies at once
        (see _get_item_boms_native_batch). Native is now the source of truth — with Blend frozen,
        formula edits land only in native, so the legacy custom field is a stale snapshot.

        Legacy path (fallback): the custrecord_blend_bom_assembly SuiteQL join, kept only for the
        few assemblies that lack a native master-default mapping. The old REST helpers
        (_resolve_current_revision / _get_components_by_revision) are retained only for the A/B diff.

        Returns (components, source, revision_id, has_bom, ok). `ok` is False when a NetSuite call
        ERRORED (429 exhausted, connection, etc.) — the empty result is then "unknown", not a
        confirmed "no BOM", so callers must NOT persist/overwrite the cache with it.
        """
        try:
            # Native via SuiteQL (assemblyItemBom.currentrevision) — no REST record fetch.
            components, revision_id = await self._get_item_bom_native(item_id)
            if components:
                return components, "native", revision_id, True, True

            # Fallback: legacy Blend field, for assemblies without a native master-default mapping.
            components = await self._get_item_bom_legacy(item_id)
            if components:
                return components, "legacy", None, True, True

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
        """Return (components, source) from cache (components may be [] for a negative cache), or
        None on a miss/stale/error. source is 'native' | 'legacy' as persisted by the last resolve.

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
                    return [], formula.source  # negative cache: item has no BOM

                rows = await get_bom_components(session, int(item_id))
                return [self._component_row_to_dict(r) for r in rows], formula.source
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

            # Batched: resolve each group of assemblies in ONE SuiteQL per source instead of one
            # call (or a REST call) per assembly. NATIVE batch (assemblyItemBom.currentrevision, no
            # REST) is the primary path and the source of truth; the legacy batch
            # (custrecord_blend_bom_assembly join) is a fallback for the few assemblies without a
            # native master-default mapping. Both write hits directly; only genuine no-BOM items or
            # a whole-batch failure fall back to the vetted per-item refresh_bom_formula, so
            # coverage never regresses.
            refreshed, errors, done = 0, 0, 0
            BATCH_SIZE = 50
            try:
                for start_idx in range(0, len(ids), BATCH_SIZE):
                    batch = [str(x) for x in ids[start_idx:start_idx + BATCH_SIZE]]
                    try:
                        native_map = await self._get_item_boms_native_batch(batch)
                    except Exception as e:
                        logger.warning(
                            f"[BOM-refresh] batch native query failed for {len(batch)} items: {e}; "
                            f"falling back to legacy/per-item"
                        )
                        native_map = {}

                    # Legacy batch only for what native didn't cover. On failure, those items drop to
                    # the per-item path below rather than regressing coverage.
                    legacy_ids = [iid for iid in batch if iid not in native_map]
                    try:
                        legacy_map = (
                            await self._get_item_boms_legacy_batch(legacy_ids) if legacy_ids else {}
                        )
                    except Exception as e:
                        logger.warning(
                            f"[BOM-refresh] batch legacy query failed for {len(legacy_ids)} items: {e}; "
                            f"falling back to per-item"
                        )
                        legacy_map = {}

                    for iid in batch:
                        try:
                            if iid in native_map:
                                entry = native_map[iid]
                                await self._write_bom_to_db(
                                    iid, entry["components"], "native", entry.get("revision_id"), True
                                )
                                await self._invalidate_bom_in_memory(iid, entry.get("parent_sku"))
                            elif iid in legacy_map:
                                entry = legacy_map[iid]
                                await self._write_bom_to_db(iid, entry["components"], "legacy", None, True)
                                await self._invalidate_bom_in_memory(iid, entry.get("parent_sku"))
                            else:
                                # No batch rows (genuine no-BOM, or a whole-batch failure): vetted
                                # per-item path — re-checks native then legacy (both SuiteQL now) and
                                # raises on NetSuite error so a good cached formula is never clobbered.
                                await self.refresh_bom_formula(iid)
                            refreshed += 1
                        except Exception as e:
                            errors += 1
                            logger.warning(f"[BOM-refresh] item {iid} failed: {e}")
                        done += 1

                    _refresh_status.update({"done": done, "errors": errors})
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

    async def _get_item_boms_legacy_batch(self, item_ids: List[str]) -> Dict[str, Dict]:
        """Batched legacy BOM resolution: ONE SuiteQL for many assemblies via parent_item.id IN (...).

        Same rows as _get_item_bom_legacy, grouped by parent. Returns
        {assembly_item_id: {"parent_sku": <sku>, "components": [<component dicts>]}}. Assemblies with
        no legacy rows are simply absent from the map (caller falls back to native per-item). Also
        carries parent_sku so callers can invalidate the in-memory BOM cache without a per-item
        get_item_details lookup. Raises on NetSuite error (caller must not clobber the cache).
        """
        if not item_ids:
            return {}
        for iid in item_ids:
            validate_numeric_id(iid, "item_id")
        id_list = ",".join(f"'{iid}'" for iid in item_ids)

        sql = f"""
        SELECT
            parent_item.id AS parent_id,
            parent_item.itemid AS parent_sku,
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
        WHERE parent_item.id IN ({id_list})
        AND item.id != 5837
        AND rev.isInactive = 'F'
        AND (rev.effectiveenddate IS NULL OR rev.effectiveenddate >= CURRENT_DATE)
        AND (rev.effectivestartdate IS NULL OR rev.effectivestartdate <= CURRENT_DATE)
        ORDER BY parent_item.id, b.id, item.id, component.quantity
        """
        start_time = time.time()
        result = await self.netsuite_service.execute_suiteql(sql)
        rows = result.get('items', [])
        grouped: Dict[str, Dict] = {}
        for row in rows:
            pid = str(row.pop("parent_id", "") or "")
            psku = row.pop("parent_sku", "") or ""
            if not pid:
                continue
            entry = grouped.setdefault(pid, {"parent_sku": psku, "components": []})
            entry["components"].append(row)
        elapsed = time.time() - start_time
        logger.info(
            f"[TIMING] _get_item_boms_legacy_batch for {len(item_ids)} assemblies took {elapsed:.3f}s, "
            f"{len(grouped)} had legacy BOMs, {len(rows)} rows"
        )
        return grouped

    async def _get_item_boms_native_batch(self, item_ids: List[str]) -> Dict[str, Dict]:
        """Batched NATIVE BOM resolution: ONE SuiteQL for many assemblies via
        assemblyItemBom.assembly IN (...), with NO REST record call.

        assemblyItemBom is the standard NetSuite table mapping an assembly item to its Bill of
        Materials; its `currentrevision` column is the current bomRevision (NetSuite already picks
        it), and `assembly` is a scalar filterable id — so unlike bom.restricttoassemblies (a
        non-filterable multi-select, the reason the old code fell back to REST) we can join straight
        through to the component lines and batch the whole set. Standard-table based, so it keeps
        working after the Blend custom field (custrecord_blend_bom_assembly) is cleared.

        Same component row shape as _get_item_bom_legacy / _get_components_by_revision. Returns
        {assembly_item_id: {"parent_sku": <sku>, "revision_id": <str>, "components": [<dicts>]}}.
        Assemblies with no master-default BOM are simply absent (caller treats as no-BOM / per-item
        fallback). Raises on NetSuite error (caller must not clobber the cache).
        """
        if not item_ids:
            return {}
        for iid in item_ids:
            validate_numeric_id(iid, "item_id")
        id_list = ",".join(f"'{iid}'" for iid in item_ids)

        sql = f"""
        SELECT
            aib.assembly AS parent_id,
            parent_item.itemid AS parent_sku,
            aib.currentrevision AS revision_id,
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
        FROM assemblyItemBom aib
        JOIN bomRevisionComponentMember AS component ON component.bomRevision = aib.currentrevision
        JOIN bom as b ON aib.billofmaterials = b.id
        JOIN item ON component.item = item.id
        JOIN item parent_item ON parent_item.id = aib.assembly
        LEFT JOIN ItemUnit as iu ON component.units = iu.key
        WHERE aib.assembly IN ({id_list})
        AND aib.masterdefault = 'T'
        AND aib.inactive = 'No'
        AND item.id != 5837
        ORDER BY aib.assembly, b.id, item.id, component.quantity
        """
        start_time = time.time()
        result = await self.netsuite_service.execute_suiteql(sql)
        rows = result.get('items', [])
        grouped: Dict[str, Dict] = {}
        for row in rows:
            pid = str(row.pop("parent_id", "") or "")
            psku = row.pop("parent_sku", "") or ""
            rev = str(row.pop("revision_id", "") or "") or None
            if not pid:
                continue
            entry = grouped.setdefault(pid, {"parent_sku": psku, "revision_id": rev, "components": []})
            entry["components"].append(row)
        elapsed = time.time() - start_time
        logger.info(
            f"[TIMING] _get_item_boms_native_batch for {len(item_ids)} assemblies took {elapsed:.3f}s, "
            f"{len(grouped)} had native BOMs, {len(rows)} rows"
        )
        return grouped

    async def _get_item_bom_native(self, item_id: str):
        """Single-assembly native BOM via SuiteQL (assemblyItemBom.currentrevision), no REST.

        Thin wrapper over _get_item_boms_native_batch so the batch query is the single source of
        truth. Returns (components, revision_id); ([], None) when the item has no master-default BOM.
        """
        grouped = await self._get_item_boms_native_batch([str(item_id)])
        entry = grouped.get(str(item_id))
        if not entry:
            return [], None
        return entry["components"], entry.get("revision_id")

    async def _invalidate_bom_in_memory(self, item_id: str, sku: Optional[str]) -> None:
        """Drop the in-memory BOM layers for an item using an already-known SKU (no NetSuite call)."""
        if not self.cache_manager:
            return
        await self.cache_manager.invalidate(make_bom_revision_cache_key(item_id))
        if sku:
            await self.cache_manager.invalidate(make_bom_cache_key(sku))

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

    async def _item_details_from_db(self, item_ids: List[str]) -> Dict[str, Dict]:
        """Build item details from our own data — display name from the items table, manufacturing
        flag from the recipe cache (an item with a cached recipe is, by definition, manufactured).

        Returns {id: details} ONLY for ids we can confirm: present in the items table AND with a
        cached recipe (has_bom=True). Everything else is omitted so the caller falls back to
        NetSuite — so we never guess an item's manufacturing status. Same row shape as
        get_item_details (itemtype is reported 'Assembly' for these confirmed manufactured items,
        which is all the batch path uses it for).
        """
        if not BOM_DB_CACHE_ENABLED or not item_ids:
            return {}
        try:
            from sqlalchemy import select
            from app.database.connection import get_session_factory
            from app.database.models import ItemDB, BOMFormulaDB

            int_ids = [int(i) for i in item_ids]
            factory = get_session_factory()
            async with factory() as session:
                item_rows = (await session.execute(
                    select(ItemDB.id, ItemDB.sku, ItemDB.name).where(ItemDB.id.in_(int_ids))
                )).all()
                item_map = {str(r.id): (r.sku, r.name) for r in item_rows}
                formula_rows = (await session.execute(
                    select(BOMFormulaDB.assembly_item_id, BOMFormulaDB.has_bom).where(
                        BOMFormulaDB.assembly_item_id.in_(int_ids)
                    )
                )).all()
                has_bom_map = {str(r.assembly_item_id): r.has_bom for r in formula_rows}

            out: Dict[str, Dict] = {}
            for iid in item_ids:
                iid = str(iid)
                if iid in item_map and has_bom_map.get(iid):  # in catalog AND has a recipe
                    sku, name = item_map[iid]
                    out[iid] = {
                        "id": iid,
                        "itemid": sku,
                        "displayname": name or sku,
                        "itemtype": "Assembly",
                        "description": name,
                        "is_manufacturing": "true",
                    }
            return out
        except Exception as e:
            logger.warning(f"[item-details] DB read failed ({e}); falling back to NetSuite")
            return {}

    async def get_item_details_bulk(self, item_ids: List[str]) -> Dict[str, Dict]:
        """Fetch details for many item ids and populate the in-memory item-details cache. Same row
        shape as get_item_details. Lookup order: in-memory cache -> our own DB (name from the items
        table + manufacturing flag from the recipe cache) -> ONE SuiteQL for whatever is left. Only
        cache-misses are queried; returns {id: details}.
        """
        out: Dict[str, Dict] = {}
        misses: List[str] = []
        for iid in item_ids:
            iid = str(iid)
            if self.cache_manager:
                cached = await self.cache_manager.get(make_item_details_cache_key(iid))
                if cached is not None:
                    out[iid] = cached
                    continue
            misses.append(iid)

        # Dedup misses, preserve order.
        misses = list(dict.fromkeys(misses))
        if not misses:
            return out

        # DB read-through: serve details we can build from our own data (name from the items table,
        # manufacturing flag from the recipe cache) so the hourly partner sweep stops re-fetching
        # item details from NetSuite. Only ids we can't confirm fall through to NetSuite.
        db_details = await self._item_details_from_db(misses)
        for iid, det in db_details.items():
            out[iid] = det
            if self.cache_manager:
                await self.cache_manager.set(make_item_details_cache_key(iid), det)
        misses = [i for i in misses if i not in db_details]
        if not misses:
            return out

        for iid in misses:
            validate_numeric_id(iid, "item_id")
        id_list = ",".join(f"'{i}'" for i in misses)
        sql = f"""
        SELECT
            id,
            itemid,
            COALESCE(description, itemid) as displayname,
            itemtype,
            description,
            CASE WHEN itemtype IN ('Assembly', 'Kit') THEN 'true' ELSE 'false' END as is_manufacturing
        FROM item
        WHERE id IN ({id_list})
        AND isinactive = 'F'
        """
        start_time = time.time()
        result = await self.netsuite_service.execute_suiteql(sql)
        rows = result.get('items', [])
        logger.info(f"[TIMING] get_item_details_bulk for {len(misses)} ids took {time.time() - start_time:.3f}s, {len(rows)} rows")
        for row in rows:
            rid = str(row.get("id"))
            out[rid] = row
            if self.cache_manager:
                await self.cache_manager.set(make_item_details_cache_key(rid), row)
        return out

    async def get_full_bom(self, item_sku: str, max_depth=5, current_depth=0, item_id: Optional[str] = None) -> List[Dict]:
        """Fetch an item's BOM by SKU, expanding per SOURCE.

        A node's BOM is expanded based on where it came from:
          - native source -> FLAT: a manufactured sub-assembly line (e.g. a made-to-stock
            concentrate) is a stocked leaf, not exploded.
          - legacy source -> MULTI-LEVEL: recurse into manufacturing sub-assemblies, as before, so
            the legacy fallback stays a faithful (correct) multi-level BOM.
        Each level re-decides, so a mixed tree resolves correctly. `max_depth` bounds the legacy
        recursion; `current_depth` offsets the returned level.

        item_id, when passed, is the already-known internal id for item_sku — skips the SKU->id
        NetSuite lookup.
        """
        start_time = time.time()

        # In-memory full-BOM cache.
        if self.cache_manager:
            cache_key = make_bom_cache_key(item_sku)
            cached_bom = await self.cache_manager.get(cache_key)
            if cached_bom is not None:
                adjusted = [dict(c, level=c.get("level", 0) + current_depth) for c in cached_bom]
                logger.info(f"[CACHE HIT] get_full_bom for {item_sku}: {len(adjusted)} components")
                return adjusted

        if current_depth > max_depth:
            return []

        if not item_id:
            item_id = await self.get_item_id_by_sku(item_sku)
        if not item_id:
            return []

        components, source = await self._get_item_bom_with_source(item_id)
        full_bom: List[Dict] = []
        for comp in components:
            node = dict(comp, level=current_depth)
            full_bom.append(node)
            # Legacy BOMs are multi-level: expand manufacturing sub-assemblies (native stays flat).
            if source == "legacy" and comp.get("is_manufacturing") == "true" and comp.get("internal_id"):
                full_bom.extend(await self.get_full_bom(
                    comp["component_sku"], max_depth, current_depth + 1, item_id=comp["internal_id"]
                ))

        if self.cache_manager and full_bom:
            base_bom = [dict(c, level=c.get("level", current_depth) - current_depth) for c in full_bom]
            await self.cache_manager.set(make_bom_cache_key(item_sku), base_bom)

        logger.info(
            f"[TIMING] get_full_bom for {item_sku} took {time.time() - start_time:.3f}s, "
            f"{len(full_bom)} components (source={source})"
        )
        return full_bom

    async def get_full_boms_batch(self, roots: List[tuple]) -> List[List[Dict]]:
        """Resolve the flat native BOMs for many assemblies in ONE SuiteQL (assemblyItemBom),
        instead of one query per root.

        roots: list of (item_sku, item_id) — item_id is the assembly's internal id (or None).
        Returns a list of component lists aligned to `roots` order (each row at level 0).

        Native BOMs are flat: a manufactured sub-assembly line (e.g. a made-to-stock concentrate)
        is treated as a stocked leaf, NOT exploded — so the single batched query IS the complete
        BOM for every root and no recursion is needed.

        Cache order per root: in-memory SKU-level cache -> persisted DB recipe cache (read-through,
        no NetSuite — this is what the weekly refresh keeps warm) -> ONE batched NetSuite query for
        whatever is cached nowhere. This matters for the hourly partner sweep: without the DB read,
        the 1h in-memory cache expires each hour and every recipe re-hits NetSuite even though we
        have it persisted.
        """
        results: List[Optional[List[Dict]]] = [None] * len(roots)

        fetch_idx: List[int] = []
        for k, (sku, iid) in enumerate(roots):
            iid_s = str(iid) if iid else None

            # 1. In-memory full-BOM cache (fastest).
            if self.cache_manager:
                cached = await self.cache_manager.get(make_bom_cache_key(sku))
                if cached is not None:
                    results[k] = [dict(c) for c in cached]
                    continue

            # 2. Persisted DB recipe cache (read-through, NO NetSuite). Native is flat -> serve
            #    directly and warm the in-memory layer; legacy needs source-gated multi-level, so
            #    defer to get_full_bom (itself DB-served per node). A stale/missing formula returns
            #    None and falls through to the NetSuite batch.
            if iid_s:
                db = await self._read_bom_from_db(iid_s)
                if db is not None:
                    comps, src = db
                    if src == "native":
                        full = [dict(c, level=0) for c in comps]
                        results[k] = full
                        if self.cache_manager:
                            await self.cache_manager.set(make_bom_cache_key(sku), full)
                    else:
                        results[k] = await self.get_full_bom(sku, item_id=iid_s)
                    continue

            # 3. Cached nowhere -> resolve from NetSuite (batched below).
            fetch_idx.append(k)

        # ONE batched native query for all uncached ids.
        ids = [str(roots[k][1]) for k in fetch_idx if roots[k][1]]
        native_map: Dict[str, Dict] = {}
        if ids:
            try:
                native_map = await self._get_item_boms_native_batch(ids)
            except Exception as e:
                logger.warning(f"[BOM] batch native query failed ({e}); falling back to legacy per-root")
                native_map = {}

        for k in fetch_idx:
            sku, iid = roots[k]
            iid = str(iid) if iid else None
            entry = native_map.get(iid) if iid else None
            if entry is not None:
                full = [dict(c, level=0) for c in entry["components"]]
                if self.cache_manager and full:
                    await self.cache_manager.set(make_bom_cache_key(sku), full)
                await self._write_bom_to_db(iid, entry["components"], "native", entry.get("revision_id"), True)
                results[k] = full
            else:
                # No native master-default BOM (or the batch failed): fall back to the per-root
                # resolver, which multi-level-expands a legacy BOM (faithful) and stays flat for a
                # native one — so the fallback is correct, not a thin flat list.
                results[k] = await self.get_full_bom(sku, item_id=iid)

        return [r if r is not None else [] for r in results]

    async def get_item_by_sku(self, item_sku: str) -> Optional[Dict]:
        """Get item details by SKU (used by production_service)."""
        item_id = await self.get_item_id_by_sku(item_sku)
        if not item_id:
            return None
        return await self.get_item_details(item_id)
