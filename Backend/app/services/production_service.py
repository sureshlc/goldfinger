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
    make_inventory_cache_key
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

        cache_key = make_inventory_cache_key(item_ids, location_name)
        cached = await self.cache_manager.get(cache_key)

        if cached is not None:
            logger.debug(f"Inventory cache HIT for {len(item_ids)} items")
            return cached

        result = await self.inventory_service.get_inventory_levels(item_ids, location_name)
        await self.cache_manager.set(cache_key, result)
        logger.debug(f"Cached inventory for {len(item_ids)} items")
        return result

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
