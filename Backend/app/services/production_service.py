"""
ProductionService with selective caching integrated.

Caching Strategy:
- BOM structures: CACHED (1 hour default)
- Item details: CACHED (1 hour default)
- SKU/ID resolution: CACHED (1 hour default)
- Inventory levels: CACHED (5 minutes default) - short TTL for near-real-time accuracy
"""
from typing import List, Dict, Optional, Tuple
import asyncio
import math
import logging
import time

from app.services.bom_service import BOMService
from app.services.inventory_service import InventoryService
from app.services.netsuite_service import NetSuiteService
from app.utils.identifier_resolution import resolve_sku_or_id
from app.utils.cache_manager import (
    CacheManager,
    make_bom_cache_key,
    make_item_details_cache_key,
    make_resolution_cache_key,
    make_inventory_cache_key,
    make_single_inventory_cache_key,
)

logger = logging.getLogger(__name__)


def consolidate_shortages(shortages: List[Dict]) -> List[Dict]:
    consolidated = {}
    for shortage in shortages:
        item_id = shortage["item_id"]
        if item_id not in consolidated:
            consolidated[item_id] = shortage
        else:
            existing_qty = consolidated[item_id].get("shortage_quantity", 0)
            additional_qty = shortage.get("shortage_quantity", 0)
            consolidated[item_id]["shortage_quantity"] = existing_qty + additional_qty
            if "required_quantity" in shortage:
                existing_req = consolidated[item_id].get("required_quantity", 0)
                consolidated[item_id]["required_quantity"] = existing_req + shortage["required_quantity"]
    return list(consolidated.values())


def safe_floor_div(x: float, y: float) -> int:
    if y <= 0:
        return 0
    try:
        return math.floor(x / y)
    except Exception as e:
        logger.error(f"Error dividing {x} by {y}: {e}")
        return 0


class ProductionService:
    def __init__(
        self,
        netsuite_service: Optional[NetSuiteService] = None,
        enable_cache: bool = True,
        bom_ttl_seconds: int = 3600,
        item_details_ttl_seconds: int = 3600,
        inventory_ttl_seconds: int = 300
    ):
        self.netsuite_service = netsuite_service or NetSuiteService()

        self.cache_manager = None
        if enable_cache:
            self.cache_manager = CacheManager(
                bom_ttl_seconds=bom_ttl_seconds,
                item_details_ttl_seconds=item_details_ttl_seconds,
                inventory_ttl_seconds=inventory_ttl_seconds
            )
            logger.info(
                f"ProductionService initialized WITH caching "
                f"(BOM TTL: {bom_ttl_seconds}s, Item Details TTL: {item_details_ttl_seconds}s, "
                f"Inventory TTL: {inventory_ttl_seconds}s)"
            )
        else:
            logger.info("ProductionService initialized WITHOUT caching")

        self.bom_service = BOMService(self.netsuite_service, self.cache_manager)
        self.inventory_service = InventoryService(self.netsuite_service)

        self.water_sku = "1229999"
        self.water_id = "1210"

    async def _resolve_identifier(self, identifier: str) -> Optional[str]:
        if self.cache_manager is None:
            return await resolve_sku_or_id(identifier, self.bom_service)

        cache_key = make_resolution_cache_key(identifier)
        cached_result = await self.cache_manager.get(cache_key)

        if cached_result is not None:
            logger.debug(f"Resolution cache hit for {identifier} -> {cached_result}")
            return cached_result

        resolved_id = await resolve_sku_or_id(identifier, self.bom_service)

        if resolved_id:
            await self.cache_manager.set(cache_key, resolved_id)
            logger.debug(f"Cached resolution: {identifier} -> {resolved_id}")

        return resolved_id

    async def _get_item_details(self, item_id: str) -> Optional[Dict]:
        return await self.bom_service.get_item_details(item_id)

    async def _get_bom(self, item_sku: str) -> List[Dict]:
        return await self.bom_service.get_full_bom(item_sku)

    async def _get_inventory(self, item_ids: List[str], location_name: Optional[str] = None) -> List[Dict]:
        if self.cache_manager is None:
            return await self.inventory_service.get_inventory_levels(item_ids, location_name)

        # Per-component caching: check each item individually
        cache_keys = {iid: make_single_inventory_cache_key(iid, location_name) for iid in item_ids}
        cached_results = await self.cache_manager.get_many(list(cache_keys.values()))

        # Split into hits and misses
        key_to_id = {v: k for k, v in cache_keys.items()}
        hits = []
        uncached_ids = []
        for iid in item_ids:
            key = cache_keys[iid]
            if key in cached_results:
                hits.append(cached_results[key])
            else:
                uncached_ids.append(iid)

        logger.info(f"Inventory cache: {len(hits)} hits, {len(uncached_ids)} misses")

        if not uncached_ids:
            return hits

        # Fetch only uncached IDs from NetSuite
        fresh = await self.inventory_service.get_inventory_levels(uncached_ids, location_name)

        # Cache each new result individually
        to_cache = {}
        for inv in fresh:
            inv_id = inv.get("item_id", "")
            if inv_id and inv_id in cache_keys:
                to_cache[cache_keys[inv_id]] = inv
        if to_cache:
            await self.cache_manager.set_many(to_cache)

        return hits + fresh

    async def get_max_producible_quantity_and_shortages(
        self,
        item_id: str,
        desired_quantity: int = 1,
        location_name: Optional[str] = None,
        bom_components: Optional[List[Dict]] = None,
        depth: int = 0,
    ) -> Tuple[int, List[Dict], Dict[str, float], Dict[str, Dict], Optional[Dict]]:
        start_time = time.time()
        indent = "  " * depth
        logger.info(f"{indent}[TIMING] get_max_producible called for item {item_id}, qty {desired_quantity}, depth {depth}")

        resolved_id = await self._resolve_identifier(item_id)
        if not resolved_id:
            logger.warning(f"{indent}Could not resolve item identifier: {item_id}")
            return 0, [{"item_id": item_id, "reason": "Could not resolve item"}], {}, {}, None
        item_id = resolved_id

        item_details = await self._get_item_details(item_id)
        if not item_details:
            logger.warning(f"{indent}Item not found: {item_id}")
            return 0, [{"item_id": item_id, "reason": "Item not found"}], {}, {}, None

        logger.info(f"{indent}Calculating feasibility for Item ID {item_id} - Desired Qty: {desired_quantity}")

        is_manufacturing = item_details.get("is_manufacturing") == "true"

        if bom_components is None:
            item_sku = item_details.get("itemid", item_id)
            logger.info(f"{indent}Fetching inventory + BOM in parallel for item {item_id} / SKU {item_sku}")
            inventory_task = self._get_inventory([item_id], location_name)
            bom_task = self._get_bom(item_sku)
            inventory_levels, bom_components = await asyncio.gather(inventory_task, bom_task)
            logger.info(f"{indent}BOM fetch returned {len(bom_components)} components")
        else:
            inventory_levels = await self._get_inventory([item_id], location_name)

        inventory_qty = float(inventory_levels[0].get("available_quantity", 0)) if inventory_levels else 0
        logger.info(f"{indent}Inventory quantity for {item_id}: {inventory_qty}")

        direct_components = [c for c in bom_components if c.get("level") == 0]
        has_sub_bom = bool(direct_components)
        logger.info(f"{indent}Direct components (level 0): {len(direct_components)}, has_sub_bom: {has_sub_bom}")

        if not is_manufacturing:
            logger.info(f"{indent}Item {item_id} is non-manufacturing. Returning inventory units: {int(inventory_qty)}")
            elapsed = time.time() - start_time
            logger.info(f"{indent}[TIMING] get_max_producible for {item_id} at depth {depth} took {elapsed:.3f}s")
            return int(inventory_qty), [], {}, {}, None

        if not has_sub_bom:
            logger.warning(f"{indent}Item {item_id} is marked as manufacturing but has no BOM components!")
            shortage = [{
                "item_id": item_id,
                "item_name": item_details.get("displayname", ""),
                "item_sku": item_details.get("itemid", ""),
                "required_quantity": desired_quantity,
                "available_quantity": inventory_qty,
                "shortage_quantity": max(0, desired_quantity - inventory_qty),
                "unit": "EA",
                "reason": "Manufacturing item with no BOM defined"
            }]
            elapsed = time.time() - start_time
            logger.info(f"{indent}[TIMING] get_max_producible for {item_id} at depth {depth} took {elapsed:.3f}s")
            return int(inventory_qty), shortage if inventory_qty < desired_quantity else [], {}, {}, None

        all_shortages = []
        component_totals = {}
        inventory_data = {}

        limiting_component_info = None
        min_producible = float('inf')

        component_skus = list({comp.get("component_sku", "") for comp in direct_components})
        resolution_results = await asyncio.gather(
            *(self._resolve_identifier(sku) for sku in component_skus)
        )
        resolved_ids = [rid for rid in resolution_results if rid]

        component_inventory_levels = await self._get_inventory(resolved_ids, location_name)

        inventory_lookup_by_sku = {inv["item_sku"]: inv for inv in component_inventory_levels}
        inventory_lookup_by_id = {inv["item_id"]: inv for inv in component_inventory_levels if "item_id" in inv}
        sku_to_id = {inv["item_sku"]: inv["item_id"] for inv in component_inventory_levels if "item_id" in inv}

        for inv in component_inventory_levels:
            if "item_id" in inv:
                inventory_data[inv["item_id"]] = inv

        max_quantities = []

        for comp in direct_components:
            comp_sku = comp.get("component_sku", "")
            comp_name = comp.get("component_displayname", comp.get("displayname", ""))
            unit = comp.get("unit")
            required_qty_per_unit = float(comp.get("quantity_required", 0))
            required_qty_total = required_qty_per_unit * desired_quantity
            comp_id = sku_to_id.get(comp_sku) or await self._resolve_identifier(comp_sku)

            if not comp_id:
                logger.warning(f"{indent}Could not resolve component SKU: {comp_sku}")
                all_shortages.append({
                    "item_id": comp_sku,
                    "item_name": comp_name,
                    "item_sku": comp_sku,
                    "required_quantity": required_qty_total,
                    "available_quantity": 0,
                    "shortage_quantity": required_qty_total,
                    "unit": unit,
                    "reason": "Component SKU not resolvable"
                })
                component_totals[comp_sku] = 0
                max_quantities.append(0)

                if 0 < min_producible:
                    min_producible = 0
                    limiting_component_info = {
                        "item_id": comp_sku,
                        "item_name": comp_name,
                        "item_sku": comp_sku,
                        "reason": "Component SKU not resolvable"
                    }
                continue

            if comp_sku == self.water_sku or comp_id == self.water_id:
                logger.info(f"{indent}Component {comp_name} treated as infinite (water).")
                component_totals[comp_id] = math.inf
                max_quantities.append(math.inf)
                continue

            is_sub_multi_level = comp.get("is_manufacturing") == "true"

            if is_sub_multi_level:
                current_index = None
                for idx, c in enumerate(bom_components):
                    if (c.get("component_sku") == comp_sku and
                        c.get("level", 0) == comp.get("level", 0)):
                        current_index = idx
                        break

                if current_index is not None:
                    current_level = comp.get("level", 0)
                    sub_components = []

                    for i in range(current_index + 1, len(bom_components)):
                        next_comp = bom_components[i]
                        next_level = next_comp.get("level", 0)

                        if next_level <= current_level:
                            break

                        sub_components.append(next_comp)

                    adjusted_sub_components = []
                    for sc in sub_components:
                        adjusted = sc.copy()
                        adjusted["level"] = sc.get("level", 0) - current_level - 1
                        adjusted_sub_components.append(adjusted)
                else:
                    adjusted_sub_components = []

                sub_max_qty, sub_shortages, sub_totals, sub_inventory, sub_limiting = await self.get_max_producible_quantity_and_shortages(
                    comp_id, int(math.ceil(required_qty_total)), location_name, adjusted_sub_components, depth + 1
                )
                all_shortages.extend(sub_shortages)

                inventory_data.update(sub_inventory)

                component_inv_qty = float(inventory_lookup_by_id.get(comp_id, {}).get("available_quantity", 0))
                total_units = component_inv_qty + sub_max_qty

                logger.info(f"{indent}Subcomponent BOM parent {comp_name} (SKU {comp_sku}) at depth {depth}: "
                            f"inventory={component_inv_qty}, max producible from subcomponents={sub_max_qty}, "
                            f"total units available={total_units}, required={required_qty_total}")

                component_totals[comp_id] = total_units

                if comp_id in inventory_data:
                    inventory_data[comp_id]["available_quantity"] = total_units
                else:
                    inventory_data[comp_id] = {"available_quantity": total_units}

                max_units_for_parent = safe_floor_div(total_units, required_qty_per_unit)

                if max_units_for_parent < min_producible or (max_units_for_parent == min_producible and is_sub_multi_level):
                    min_producible = max_units_for_parent
                    limiting_component_info = {
                        "item_id": comp_id,
                        "item_name": comp_name,
                        "item_sku": comp_sku,
                        "max_units_possible": max_units_for_parent,
                        "total_available": total_units,
                        "required_per_unit": required_qty_per_unit,
                        "sub_limiting": sub_limiting,
                        "is_assembly": True
                    }

                if total_units < required_qty_total:
                    all_shortages.append({
                        "item_id": comp_id,
                        "item_name": comp_name,
                        "item_sku": comp_sku,
                        "required_quantity": required_qty_total,
                        "available_quantity": total_units,
                        "shortage_quantity": required_qty_total - total_units,
                        "unit": unit,
                        "reason": "Insufficient inventory and subcomponent production"
                    })

            else:
                component_inv_qty = float(inventory_lookup_by_id.get(comp_id, {}).get("available_quantity", 0))

                component_totals[comp_id] = component_inv_qty

                max_units_for_parent = safe_floor_div(component_inv_qty, required_qty_per_unit)
                logger.info(f"{indent}Leaf component {comp_name}: inventory={component_inv_qty}, "
                            f"required_qty_per_unit={required_qty_per_unit}, required_total={required_qty_total}, "
                            f"max_units_for_parent={max_units_for_parent}")

                if max_units_for_parent < min_producible:
                    min_producible = max_units_for_parent
                    limiting_component_info = {
                        "item_id": comp_id,
                        "item_name": comp_name,
                        "item_sku": comp_sku,
                        "max_units_possible": max_units_for_parent,
                        "available_inventory": component_inv_qty,
                        "required_per_unit": required_qty_per_unit,
                        "is_assembly": False
                    }

                if component_inv_qty < required_qty_total:
                    all_shortages.append({
                        "item_id": comp_id,
                        "item_name": comp_name,
                        "item_sku": comp_sku,
                        "required_quantity": required_qty_total,
                        "available_quantity": component_inv_qty,
                        "shortage_quantity": required_qty_total - component_inv_qty,
                        "unit": unit,
                        "reason": "Insufficient inventory"
                    })

            max_quantities.append(max_units_for_parent)

        all_shortages = consolidate_shortages(all_shortages)

        filtered_quantities = [q for q in max_quantities if q != math.inf]
        logger.info(f"{indent}DEBUG: max_quantities = {max_quantities}")
        logger.info(f"{indent}DEBUG: filtered_quantities = {filtered_quantities}")
        max_producible = int(min(filtered_quantities)) if filtered_quantities else 0

        elapsed = time.time() - start_time
        logger.info(f"{indent}[TIMING] get_max_producible for {item_id} at depth {depth} took {elapsed:.3f}s")
        logger.info(f"{indent}Returning max producible quantity: {max_producible} for item {item_id} "
                    f"at recursion depth {depth} (desired: {desired_quantity})")

        if limiting_component_info:
            logger.info(f"{indent}Limiting component: {limiting_component_info.get('item_name')} "
                       f"(max units: {limiting_component_info.get('max_units_possible')})")

        return max_producible, all_shortages, component_totals, inventory_data, limiting_component_info

    async def get_production_analysis(
        self,
        item_identifier: str,
        desired_quantity: int = 1,
        location_name: Optional[str] = None
    ) -> Dict:
        total_start = time.time()
        logger.info(f"=== [TIMING] Starting production analysis for item {item_identifier}, quantity {desired_quantity} ===")

        resolution_start = time.time()
        resolved_id = await self._resolve_identifier(item_identifier)
        logger.info(f"[TIMING] SKU resolution took {time.time() - resolution_start:.3f}s")

        if not resolved_id:
            logger.warning(f"Could not resolve item identifier: {item_identifier}")
            raise ValueError(f"Item '{item_identifier}' not found in system")

        item_id = resolved_id
        original_identifier = item_identifier

        item_details = await self._get_item_details(item_id)

        if not item_details:
            logger.warning(f"Item details not found for ID: {item_id}")
            raise ValueError(f"Item '{item_identifier}' not found in system")

        is_manufacturing = item_details.get("is_manufacturing") == "true"
        item_name = item_details.get("displayname", "")
        item_sku = item_details.get("itemid", original_identifier)

        if not is_manufacturing:
            return {
                "item_id": item_id,
                "item_name": item_name,
                "item_sku": item_sku,
                "can_produce": False,
                "max_quantity_producible": 0,
                "limiting_component": "Item is not a manufacturing item",
                "bom_components": [],
                "component_availability": [],
                "shortages": [],
                "location_name": location_name
            }

        calc_start = time.time()
        max_producible_quantity, shortages, component_totals, inventory_data, limiting_info = await self.get_max_producible_quantity_and_shortages(
            item_id, desired_quantity, location_name, None
        )

        bom_components = await self._get_bom(item_sku)

        if not bom_components:
            return {
                "item_id": item_id,
                "item_name": item_name,
                "item_sku": item_sku,
                "can_produce": False,
                "max_quantity_producible": 0,
                "limiting_component": "No BOM found for this item",
                "bom_components": [],
                "component_availability": [],
                "shortages": [],
                "location_name": location_name
            }

        for comp in bom_components:
            comp.setdefault("level", 0)
        logger.info(f"[TIMING] Production calculation took {time.time() - calc_start:.3f}s")

        can_produce = max_producible_quantity >= desired_quantity

        limiting_component = limiting_info.get("item_name") if limiting_info else None

        formatted_bom = []
        for comp in bom_components:
            formatted_bom.append({
                "item_id": comp.get("bom_id", ""),
                "item_name": comp.get("component_displayname", ""),
                "item_sku": comp.get("component_sku", ""),
                "quantity_required": round(float(comp.get("quantity_required", 0)) * desired_quantity, 5),
                "unit": comp.get("unit") or "N/A",
                "level": comp.get("level", 0)
            })

        sku_to_id = {}
        for comp in bom_components:
            comp_sku = comp.get("component_sku", "")
            comp_id = comp.get("internal_id", "")
            if comp_sku and comp_id:
                sku_to_id[comp_sku] = comp_id

        for comp_id, inv_data in inventory_data.items():
            if "item_sku" in inv_data:
                comp_sku = inv_data["item_sku"]
                if comp_sku not in sku_to_id:
                    sku_to_id[comp_sku] = comp_id

        unique_skus = [sku for sku in set(comp.get("component_sku", "") for comp in bom_components) if sku and sku not in sku_to_id]
        if unique_skus:
            resolved_results = await asyncio.gather(
                *(self._resolve_identifier(sku) for sku in unique_skus)
            )
            for sku, resolved_id in zip(unique_skus, resolved_results):
                if resolved_id:
                    sku_to_id[sku] = resolved_id

        component_availability = []
        for comp in bom_components:
            comp_sku = comp.get("component_sku", "")
            comp_name = comp.get("component_displayname", comp.get("displayname", ""))
            unit = comp.get("unit")
            required_qty_per_unit = float(comp.get("quantity_required", 0))
            required_qty_total = required_qty_per_unit * desired_quantity

            comp_id = sku_to_id.get(comp_sku, comp_sku)

            if comp_sku == self.water_sku or comp_id == self.water_id:
                component_availability.append({
                    "item_id": comp_id,
                    "item_name": comp_name,
                    "item_sku": comp_sku,
                    "required_quantity": required_qty_total,
                    "available_quantity": 999999,
                    "display_quantity": "Unlimited",
                    "raw_inventory": 999999,
                    "required_for_desired_qty": required_qty_total,
                    "sufficient": True,
                    "max_units_possible": 999999,
                    "unit": unit
                })
                continue

            inv_record = inventory_data.get(comp_id, {})
            raw_inventory = float(inv_record.get("available_quantity", 0))

            total_available = component_totals.get(comp_id, raw_inventory)

            if total_available == math.inf:
                sufficient = True
                max_units_possible = math.inf
            else:
                sufficient = total_available >= required_qty_total
                max_units_possible = math.floor(total_available / required_qty_per_unit) if required_qty_per_unit > 0 else 0

            component_availability.append({
                "item_id": comp_id,
                "item_name": comp_name,
                "item_sku": comp_sku,
                "required_quantity": required_qty_total,
                "available_quantity": total_available,
                "raw_inventory": raw_inventory,
                "required_for_desired_qty": required_qty_total,
                "sufficient": sufficient,
                "max_units_possible": max_units_possible if max_units_possible != math.inf else 999999,
                "unit": unit
            })

        elapsed = time.time() - total_start
        logger.info(f"=== [TIMING] Total production analysis took {elapsed:.3f}s ===")

        return {
            "item_id": item_id,
            "item_name": item_name,
            "item_sku": item_sku,
            "can_produce": can_produce,
            "max_quantity_producible": max_producible_quantity,
            "limiting_component": limiting_component,
            "bom_components": formatted_bom,
            "component_availability": component_availability,
            "shortages": shortages,
            "location_name": location_name
        }

    # ========================================================================
    # BATCH FEASIBILITY — Multi-SKU analysis with shared inventory ledger
    # ========================================================================

    async def get_batch_production_analysis(
        self,
        items: List[Tuple[str, int]],  # [(sku, desired_quantity), ...]
        location_name: Optional[str] = None,
    ) -> Dict:
        """
        Analyze production feasibility for multiple SKUs simultaneously.

        Uses a shared inventory ledger so that when SKU-A and SKU-B both need
        the same raw material, the second SKU sees what's left after the first
        has been accounted for.  Items are processed in input order — the first
        item gets priority.
        """
        total_start = time.time()
        logger.info(f"=== [BATCH] Starting batch feasibility for {len(items)} SKUs ===")

        # ------------------------------------------------------------------
        # 1. Resolve all SKUs and fetch their BOMs in parallel
        # ------------------------------------------------------------------
        sku_meta: List[Dict] = []  # [{sku, desired_qty, item_id, item_name, item_sku, bom, direct_components}]

        resolve_tasks = [self._resolve_identifier(sku) for sku, _ in items]
        resolved_ids = await asyncio.gather(*resolve_tasks)

        # Fetch item details in parallel for all resolved IDs
        detail_tasks = []
        for idx, (sku, desired_qty) in enumerate(items):
            rid = resolved_ids[idx]
            if rid:
                detail_tasks.append((idx, rid, desired_qty, sku))

        item_details_results = await asyncio.gather(
            *(self._get_item_details(rid) for _, rid, _, _ in detail_tasks)
        )

        # Pair details back, fetch BOMs in parallel
        valid_entries = []
        for (idx, rid, desired_qty, orig_sku), details in zip(detail_tasks, item_details_results):
            if not details:
                logger.warning(f"[BATCH] Could not find item details for {orig_sku} (resolved: {rid})")
                sku_meta.append({
                    "sku": orig_sku, "desired_qty": desired_qty,
                    "item_id": rid, "item_name": orig_sku, "item_sku": orig_sku,
                    "bom": [], "direct_components": [], "is_manufacturing": False,
                })
                continue
            item_sku_val = details.get("itemid", orig_sku)
            is_mfg = details.get("is_manufacturing") == "true"
            valid_entries.append((idx, rid, desired_qty, orig_sku, details, item_sku_val, is_mfg))

        # Fetch BOMs for manufacturing items in parallel
        bom_tasks = []
        bom_indices = []
        for entry in valid_entries:
            idx, rid, desired_qty, orig_sku, details, item_sku_val, is_mfg = entry
            if is_mfg:
                bom_tasks.append(self._get_bom(item_sku_val))
                bom_indices.append(len(sku_meta))  # position where this will be inserted
            sku_meta.append({
                "sku": orig_sku, "desired_qty": desired_qty,
                "item_id": rid,
                "item_name": details.get("displayname", orig_sku),
                "item_sku": item_sku_val,
                "bom": [],
                "direct_components": [],
                "is_manufacturing": is_mfg,
            })

        # Also add placeholder entries for items that failed to resolve
        for idx, (sku, desired_qty) in enumerate(items):
            if resolved_ids[idx] is None:
                sku_meta.append({
                    "sku": sku, "desired_qty": desired_qty,
                    "item_id": None, "item_name": sku, "item_sku": sku,
                    "bom": [], "direct_components": [], "is_manufacturing": False,
                })

        bom_results = await asyncio.gather(*bom_tasks) if bom_tasks else []
        for bi, bom in zip(bom_indices, bom_results):
            sku_meta[bi]["bom"] = bom
            sku_meta[bi]["direct_components"] = [c for c in bom if c.get("level") == 0]

        # Maintain input order: rebuild sku_meta in the original items order
        # (currently items may be out of order because unresolved ones were appended)
        sku_meta_by_sku: Dict[str, Dict] = {}
        for m in sku_meta:
            # Use original SKU as key; first occurrence wins (preserves order)
            if m["sku"] not in sku_meta_by_sku:
                sku_meta_by_sku[m["sku"]] = m
        ordered_meta = [sku_meta_by_sku[sku] for sku, _ in items if sku in sku_meta_by_sku]

        # ------------------------------------------------------------------
        # 2. Collect ALL unique component IDs across all BOM levels
        #    (not just direct_components) so sub-assembly children are included
        # ------------------------------------------------------------------
        all_component_skus: set = set()
        for meta in ordered_meta:
            for comp in meta["bom"]:
                comp_sku = comp.get("component_sku", "")
                if comp_sku:
                    all_component_skus.add(comp_sku)

        # Resolve component SKUs → internal IDs
        comp_sku_list = list(all_component_skus)
        comp_resolve_results = await asyncio.gather(
            *(self._resolve_identifier(s) for s in comp_sku_list)
        )
        comp_sku_to_id: Dict[str, str] = {}
        resolved_comp_ids: List[str] = []
        for sku, rid in zip(comp_sku_list, comp_resolve_results):
            if rid:
                comp_sku_to_id[sku] = rid
                resolved_comp_ids.append(rid)

        # ------------------------------------------------------------------
        # 3. Batch-fetch inventory for ALL components in one call
        # ------------------------------------------------------------------
        unique_comp_ids = list(set(resolved_comp_ids))
        all_inventory = await self._get_inventory(unique_comp_ids, location_name) if unique_comp_ids else []

        # Build available-inventory map (this is the shared ledger)
        inventory_map: Dict[str, float] = {}
        comp_id_to_info: Dict[str, Dict] = {}
        for inv in all_inventory:
            cid = inv.get("item_id", "")
            inventory_map[cid] = float(inv.get("available_quantity", 0))
            comp_id_to_info[cid] = inv

        # ------------------------------------------------------------------
        # 3.5  Sub-assembly enrichment
        #      For direct components marked is_manufacturing, compute
        #      effective_availability = on_hand + producible_from_sub_components
        # ------------------------------------------------------------------
        sub_assembly_map: Dict[str, float] = {}       # comp_id -> effective_availability
        sub_assembly_recipes: Dict[str, List[Dict]] = {}  # comp_id -> [{sub_comp_id, qty_per_unit}]
        sub_assembly_on_hand: Dict[str, float] = {}   # comp_id -> raw on-hand qty

        # Gather ALL sub-assembly components across all BOMs at any level
        # (not just direct_components — a sub-assembly's child can also be a sub-assembly)
        seen_sub_assemblies: set = set()
        sub_assembly_comps: List[Dict] = []
        for meta in ordered_meta:
            bom = meta["bom"]
            for comp in bom:
                if comp.get("is_manufacturing") != "true":
                    continue
                comp_sku = comp.get("component_sku", "")
                comp_id = comp_sku_to_id.get(comp_sku)
                if not comp_id or comp_id in seen_sub_assemblies:
                    continue
                seen_sub_assemblies.add(comp_id)
                sub_assembly_comps.append({"comp": comp, "bom": bom, "comp_id": comp_id})

        # Sort by level descending so deepest sub-assemblies are processed first (bottom-up)
        sub_assembly_comps.sort(key=lambda x: x["comp"].get("level", 0), reverse=True)

        # Process sub-assemblies bottom-up (max 2 levels deep)
        MAX_SUB_DEPTH = 2
        for _depth in range(MAX_SUB_DEPTH):
            for sa in sub_assembly_comps:
                comp = sa["comp"]
                bom = sa["bom"]
                comp_id = sa["comp_id"]
                comp_sku = comp.get("component_sku", "")

                if comp_id in sub_assembly_map:
                    continue  # already computed

                # Find this component's position in the BOM and extract sub-components
                current_index = None
                for idx_b, c in enumerate(bom):
                    if (c.get("component_sku") == comp_sku and
                            c.get("level", 0) == comp.get("level", 0)):
                        current_index = idx_b
                        break

                if current_index is None:
                    continue

                current_level = comp.get("level", 0)
                recipe = []
                all_children_resolved = True

                for i in range(current_index + 1, len(bom)):
                    next_comp = bom[i]
                    next_level = next_comp.get("level", 0)
                    if next_level <= current_level:
                        break
                    # Only direct children of this sub-assembly (one level down)
                    if next_level != current_level + 1:
                        continue

                    sub_sku = next_comp.get("component_sku", "")
                    sub_id = comp_sku_to_id.get(sub_sku)
                    if not sub_id:
                        continue

                    # Skip water (treated as infinite supply)
                    if sub_sku == self.water_sku or sub_id == self.water_id:
                        continue

                    sub_qty = float(next_comp.get("quantity_required", 0))

                    # If this child is itself a sub-assembly, it must have been computed already
                    is_child_sa = next_comp.get("is_manufacturing") == "true"
                    if is_child_sa and sub_id not in sub_assembly_map:
                        all_children_resolved = False
                        break

                    recipe.append({"sub_comp_id": sub_id, "qty_per_unit": sub_qty, "sub_sku": sub_sku})

                if not all_children_resolved or not recipe:
                    continue

                # Compute max producible from sub-components
                on_hand = inventory_map.get(comp_id, 0)
                sub_assembly_on_hand[comp_id] = on_hand

                min_producible_from_subs = float('inf')
                for r in recipe:
                    sub_avail = sub_assembly_map.get(r["sub_comp_id"], inventory_map.get(r["sub_comp_id"], 0))
                    if r["qty_per_unit"] > 0:
                        min_producible_from_subs = min(min_producible_from_subs, math.floor(sub_avail / r["qty_per_unit"]))
                    else:
                        min_producible_from_subs = min(min_producible_from_subs, 0)

                if min_producible_from_subs == float('inf'):
                    min_producible_from_subs = 0

                effective = on_hand + min_producible_from_subs
                sub_assembly_map[comp_id] = effective
                sub_assembly_recipes[comp_id] = recipe
                logger.info(f"[BATCH] Sub-assembly {comp_sku} (ID {comp_id}): "
                            f"on_hand={on_hand}, producible_from_subs={min_producible_from_subs}, "
                            f"effective={effective}")

        # ------------------------------------------------------------------
        # 4. Build demand map for contention detection
        # ------------------------------------------------------------------
        component_demand: Dict[str, List[Dict]] = {}  # comp_id -> [{sku, qty_needed}]
        for meta in ordered_meta:
            for comp in meta["direct_components"]:
                comp_sku = comp.get("component_sku", "")
                comp_id = comp_sku_to_id.get(comp_sku)
                if not comp_id:
                    continue
                # Skip water (treated as infinite)
                if comp_sku == self.water_sku or comp_id == self.water_id:
                    continue
                required_per_unit = float(comp.get("quantity_required", 0))
                qty_needed = required_per_unit * meta["desired_qty"]
                if comp_id not in component_demand:
                    component_demand[comp_id] = []
                component_demand[comp_id].append({
                    "sku": meta["item_sku"],
                    "quantity_needed": qty_needed,
                })

        # ------------------------------------------------------------------
        # 5. Detect contentions (shared components where demand > supply)
        # ------------------------------------------------------------------
        material_contentions: List[Dict] = []
        for comp_id, demands in component_demand.items():
            if len(demands) < 2:
                continue  # Not shared — no contention possible
            total_demanded = sum(d["quantity_needed"] for d in demands)
            # Use effective availability for sub-assemblies
            total_available = sub_assembly_map.get(comp_id, inventory_map.get(comp_id, 0))
            if total_demanded > total_available:
                info = comp_id_to_info.get(comp_id, {})
                material_contentions.append({
                    "component_sku": info.get("item_sku", comp_id),
                    "component_name": info.get("item_name", comp_id),
                    "total_available": total_available,
                    "total_demanded": total_demanded,
                    "shortage": total_demanded - total_available,
                    "demanded_by": demands,
                })

        # ------------------------------------------------------------------
        # 6. Calculate per-SKU feasibility using the shared ledger
        #    Process in input order (first SKU gets priority).
        # ------------------------------------------------------------------
        shared_ledger = dict(inventory_map)  # copy — we'll deduct as we go

        def _effective_avail(cid: str, depth: int = 0) -> float:
            """Recursively compute effective availability for a component from shared_ledger."""
            if depth > 3 or cid not in sub_assembly_recipes:
                return max(0, shared_ledger.get(cid, 0))
            on_hand = max(0, shared_ledger.get(cid, 0))
            recipe = sub_assembly_recipes[cid]
            if not recipe:
                return on_hand
            min_prod = float('inf')
            for r in recipe:
                child_avail = _effective_avail(r["sub_comp_id"], depth + 1)
                if r["qty_per_unit"] > 0:
                    min_prod = min(min_prod, math.floor(child_avail / r["qty_per_unit"]))
                else:
                    min_prod = 0
            if min_prod == float('inf'):
                min_prod = 0
            return on_hand + min_prod

        results: List[Dict] = []

        for meta in ordered_meta:
            desired_qty = meta["desired_qty"]
            direct_components = meta["direct_components"]

            if not meta["is_manufacturing"] or not direct_components:
                # Non-manufacturing or no BOM — can't produce
                status = "blocked"
                results.append({
                    "item_sku": meta["item_sku"],
                    "item_name": meta["item_name"],
                    "desired_quantity": desired_qty,
                    "can_produce": False,
                    "max_quantity_producible": 0,
                    "limiting_component": "Not a manufacturing item" if not meta["is_manufacturing"] else "No BOM found",
                    "shortages": [],
                    "status": status,
                })
                continue

            max_producible = float('inf')
            limiting_component = None
            shortages = []

            for comp in direct_components:
                comp_sku = comp.get("component_sku", "")
                comp_name = comp.get("component_displayname", comp.get("displayname", ""))
                comp_id = comp_sku_to_id.get(comp_sku)

                if not comp_id:
                    # Unresolvable component — blocked
                    max_producible = 0
                    limiting_component = comp_name or comp_sku
                    shortages.append({
                        "item_id": comp_sku,
                        "item_name": comp_name,
                        "item_sku": comp_sku,
                        "required_quantity": float(comp.get("quantity_required", 0)) * desired_qty,
                        "available_quantity": 0,
                        "shortage_quantity": float(comp.get("quantity_required", 0)) * desired_qty,
                        "reason": "Component SKU not resolvable",
                    })
                    continue

                if comp_sku == self.water_sku or comp_id == self.water_id:
                    continue  # Infinite supply

                required_per_unit = float(comp.get("quantity_required", 0))
                required_total = required_per_unit * desired_qty

                # 2C: Use effective availability for sub-assemblies (recurses for nested)
                if comp_id in sub_assembly_recipes:
                    available = _effective_avail(comp_id)
                else:
                    available = shared_ledger.get(comp_id, 0)

                max_from_this = safe_floor_div(available, required_per_unit) if required_per_unit > 0 else 0

                if max_from_this < max_producible:
                    max_producible = max_from_this
                    limiting_component = comp_name or comp_sku

                if available < required_total:
                    shortage_entry = {
                        "item_id": comp_id,
                        "item_name": comp_name,
                        "item_sku": comp_sku,
                        "required_quantity": required_total,
                        "available_quantity": available,
                        "shortage_quantity": required_total - available,
                        "reason": "Insufficient shared inventory",
                    }
                    # 2F: Enrich sub-assembly shortages with sub-component details
                    if comp_id in sub_assembly_recipes:
                        sub_shortages = []
                        for r in sub_assembly_recipes[comp_id]:
                            sub_avail = shared_ledger.get(r["sub_comp_id"], 0)
                            sub_info = comp_id_to_info.get(r["sub_comp_id"], {})
                            sub_shortages.append({
                                "item_id": r["sub_comp_id"],
                                "item_sku": r.get("sub_sku", r["sub_comp_id"]),
                                "item_name": sub_info.get("item_name", r["sub_comp_id"]),
                                "available_quantity": sub_avail,
                                "qty_per_unit": r["qty_per_unit"],
                            })
                        shortage_entry["reason"] = "Insufficient sub-assembly production capacity"
                        shortage_entry["sub_component_details"] = sub_shortages
                    shortages.append(shortage_entry)

            if max_producible == float('inf'):
                max_producible = 0  # No components found

            max_producible = int(max_producible)
            actual_qty = min(max_producible, desired_qty)

            # Deduct consumed inventory from shared ledger
            for comp in direct_components:
                comp_sku = comp.get("component_sku", "")
                comp_id = comp_sku_to_id.get(comp_sku)
                if not comp_id or comp_sku == self.water_sku or comp_id == self.water_id:
                    continue
                required_per_unit = float(comp.get("quantity_required", 0))
                consumed = required_per_unit * actual_qty

                if comp_id in sub_assembly_recipes and consumed > 0:
                    # 2D: Sub-assembly deduction — use on-hand first, then produce remainder
                    # Recurse for nested sub-assemblies
                    def _deduct_sa(sa_id: str, qty: float, d: int = 0):
                        if d > 3 or qty <= 0:
                            return
                        on_hand_now = max(0, shared_ledger.get(sa_id, 0))
                        from_on_hand = min(qty, on_hand_now)
                        need_to_produce = math.ceil(qty - from_on_hand)
                        shared_ledger[sa_id] = max(0, on_hand_now - from_on_hand)
                        if need_to_produce > 0 and sa_id in sub_assembly_recipes:
                            for r in sub_assembly_recipes[sa_id]:
                                rm_consumed = r["qty_per_unit"] * need_to_produce
                                if r["sub_comp_id"] in sub_assembly_recipes:
                                    _deduct_sa(r["sub_comp_id"], rm_consumed, d + 1)
                                else:
                                    shared_ledger[r["sub_comp_id"]] = max(0, shared_ledger.get(r["sub_comp_id"], 0) - rm_consumed)

                    _deduct_sa(comp_id, consumed)
                else:
                    shared_ledger[comp_id] = max(0, shared_ledger.get(comp_id, 0) - consumed)

            # Classify status
            if max_producible >= desired_qty:
                status = "fully_producible"
            elif max_producible > 0:
                status = "partially_producible"
            else:
                status = "blocked"

            can_produce = max_producible >= desired_qty

            results.append({
                "item_sku": meta["item_sku"],
                "item_name": meta["item_name"],
                "desired_quantity": desired_qty,
                "can_produce": can_produce,
                "max_quantity_producible": max_producible,
                "limiting_component": limiting_component,
                "shortages": shortages,
                "status": status,
            })

        # ------------------------------------------------------------------
        # 7. Build summary
        # ------------------------------------------------------------------
        fully = sum(1 for r in results if r["status"] == "fully_producible")
        partially = sum(1 for r in results if r["status"] == "partially_producible")
        blocked = sum(1 for r in results if r["status"] == "blocked")

        summary = {
            "total_skus": len(results),
            "fully_producible": fully,
            "partially_producible": partially,
            "blocked": blocked,
            "contention_count": len(material_contentions),
        }

        elapsed = time.time() - total_start
        logger.info(f"=== [BATCH] Batch feasibility completed in {elapsed:.3f}s — "
                     f"{fully} fully, {partially} partial, {blocked} blocked, "
                     f"{len(material_contentions)} contentions ===")

        return {
            "results": results,
            "material_contentions": material_contentions,
            "summary": summary,
        }

    # Cache management methods

    async def invalidate_item_cache(self, item_id: str, item_sku: Optional[str] = None) -> None:
        """Invalidate all cached data for a specific item."""
        if self.cache_manager is None:
            logger.warning("Cache is not enabled")
            return

        details_key = make_item_details_cache_key(item_id)
        await self.cache_manager.invalidate(details_key)

        await self.cache_manager.invalidate_pattern(f"inventory:{item_id}")

        if item_sku:
            bom_key = make_bom_cache_key(item_sku)
            await self.cache_manager.invalidate(bom_key)
            logger.info(f"Invalidated cache for item {item_id} (SKU: {item_sku})")
        else:
            logger.info(f"Invalidated item details cache for item {item_id}")

    async def invalidate_all_boms(self) -> int:
        if self.cache_manager is None:
            return 0
        return await self.cache_manager.invalidate_pattern('bom:')

    async def invalidate_all_item_details(self) -> int:
        if self.cache_manager is None:
            return 0
        return await self.cache_manager.invalidate_pattern('item_details:')

    async def clear_all_caches(self) -> None:
        if self.cache_manager:
            await self.cache_manager.clear()

    async def get_cache_stats(self) -> Dict:
        if self.cache_manager:
            return await self.cache_manager.get_stats()
        return {}
