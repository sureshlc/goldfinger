"""
Unit tests for batch feasibility: per-component caching + sub-assembly support.

Usage:
    python -m pytest app/tests/test_batch_feasibility.py -v -s
    python -m app.tests.test_batch_feasibility
"""
import asyncio
import math
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List, Dict, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app.utils.cache_manager import (
    CacheManager,
    make_single_inventory_cache_key,
    make_inventory_cache_key,
)
from app.services.production_service import ProductionService


# ============================================================================
# HELPERS
# ============================================================================

def make_inventory_record(item_id: str, sku: str, qty: float, name: str = "") -> Dict:
    return {
        "item_id": item_id,
        "item_sku": sku,
        "item_name": name or sku,
        "available_quantity": qty,
    }


def make_bom_entry(
    comp_sku: str, qty: float, level: int = 0,
    displayname: str = "", is_manufacturing: str = "false",
) -> Dict:
    return {
        "component_sku": comp_sku,
        "component_displayname": displayname or comp_sku,
        "quantity_required": qty,
        "level": level,
        "is_manufacturing": is_manufacturing,
        "unit": "EA",
    }


# ============================================================================
# 1. CacheManager.get_many / set_many tests
# ============================================================================

async def test_get_many_set_many():
    """get_many returns hits; set_many stores multiple entries in one call."""
    cm = CacheManager(inventory_ttl_seconds=300)

    # set_many
    await cm.set_many({
        "inventory:100": {"item_id": "100", "available_quantity": 50},
        "inventory:200": {"item_id": "200", "available_quantity": 30},
    })

    # get_many — all hits
    results = await cm.get_many(["inventory:100", "inventory:200"])
    assert len(results) == 2
    assert results["inventory:100"]["available_quantity"] == 50
    assert results["inventory:200"]["available_quantity"] == 30

    # get_many — partial hit
    results = await cm.get_many(["inventory:100", "inventory:999"])
    assert len(results) == 1
    assert "inventory:100" in results
    assert "inventory:999" not in results

    stats = await cm.get_stats()
    assert stats["inventory"]["hits"] >= 3  # 2 from first get_many + 1 from second
    assert stats["inventory"]["misses"] >= 1

    print("  PASS: get_many / set_many")


# ============================================================================
# 2. make_single_inventory_cache_key
# ============================================================================

async def test_single_cache_key():
    """Per-component cache keys are distinct and location-aware."""
    k1 = make_single_inventory_cache_key("100")
    k2 = make_single_inventory_cache_key("200")
    k3 = make_single_inventory_cache_key("100", "Warehouse A")

    assert k1 != k2
    assert k1 != k3
    assert k1 == "inventory:100"
    assert k3 == "inventory:100|loc:Warehouse A"

    print("  PASS: make_single_inventory_cache_key")


# ============================================================================
# 3. _get_inventory per-component caching
# ============================================================================

async def test_per_component_inventory_cache():
    """
    Second call with overlapping item IDs should hit cache for known items
    and only fetch unknown items from NetSuite.
    """
    service = ProductionService(enable_cache=True)

    call_log = []

    async def mock_get_inventory_levels(item_ids: List[str], location_name=None):
        call_log.append(set(item_ids))
        return [make_inventory_record(iid, f"SKU-{iid}", 10.0) for iid in item_ids]

    service.inventory_service.get_inventory_levels = mock_get_inventory_levels

    # First call: items A, B, C — all miss
    r1 = await service._get_inventory(["A", "B", "C"])
    assert len(r1) == 3
    assert call_log[-1] == {"A", "B", "C"}

    # Second call: items B, C, D — B,C should hit cache, only D fetched
    r2 = await service._get_inventory(["B", "C", "D"])
    assert len(r2) == 3  # 2 from cache + 1 fresh
    assert call_log[-1] == {"D"}, f"Expected only D to be fetched, got {call_log[-1]}"

    # Third call: all cached
    r3 = await service._get_inventory(["A", "B", "C", "D"])
    assert len(r3) == 4
    assert len(call_log) == 2, "No new NetSuite call expected — all cached"

    print("  PASS: per-component inventory caching")


# ============================================================================
# 4. Sub-assembly enrichment in batch mode
# ============================================================================

async def test_sub_assembly_batch_feasibility():
    """
    SKU with a sub-assembly component: batch mode should account for
    on-hand + producible-from-sub-components (not just on-hand).

    BOM for FG-100 (Finished Good):
      Level 0: SA-50 (sub-assembly, is_manufacturing=true)  x2 per unit
      Level 1:   RM-10 (raw material) x3 per SA-50
      Level 1:   RM-20 (raw material) x1 per SA-50
      Level 0: RM-30 (raw material) x5 per unit

    Inventory:
      SA-50: 3 on-hand
      RM-10: 30 on-hand
      RM-20: 8  on-hand
      RM-30: 100 on-hand

    Expected for SA-50:
      producible from subs = min(30/3, 8/1) = min(10, 8) = 8
      effective = 3 + 8 = 11
    Max FG-100 from SA-50 = floor(11 / 2) = 5
    Max FG-100 from RM-30 = floor(100 / 5) = 20
    Max FG-100 = min(5, 20) = 5
    """
    service = ProductionService(enable_cache=False)

    # Mock identifier resolution: SKU -> internal ID
    sku_to_id = {
        "FG-100": "ID-FG100",
        "SA-50": "ID-SA50",
        "RM-10": "ID-RM10",
        "RM-20": "ID-RM20",
        "RM-30": "ID-RM30",
    }

    async def mock_resolve(identifier):
        return sku_to_id.get(identifier)

    service._resolve_identifier = mock_resolve

    # Mock item details
    async def mock_details(item_id):
        details_map = {
            "ID-FG100": {"itemid": "FG-100", "displayname": "Finished Good 100", "is_manufacturing": "true"},
        }
        return details_map.get(item_id)

    service._get_item_details = mock_details

    # Mock BOM
    async def mock_bom(item_sku):
        if item_sku == "FG-100":
            return [
                make_bom_entry("SA-50", 2, level=0, displayname="Sub Assy 50", is_manufacturing="true"),
                make_bom_entry("RM-10", 3, level=1, displayname="Raw Mat 10"),
                make_bom_entry("RM-20", 1, level=1, displayname="Raw Mat 20"),
                make_bom_entry("RM-30", 5, level=0, displayname="Raw Mat 30"),
            ]
        return []

    service._get_bom = mock_bom

    # Mock inventory
    inventory_data = {
        "ID-SA50": make_inventory_record("ID-SA50", "SA-50", 3, "Sub Assy 50"),
        "ID-RM10": make_inventory_record("ID-RM10", "RM-10", 30, "Raw Mat 10"),
        "ID-RM20": make_inventory_record("ID-RM20", "RM-20", 8, "Raw Mat 20"),
        "ID-RM30": make_inventory_record("ID-RM30", "RM-30", 100, "Raw Mat 30"),
    }

    async def mock_inventory(item_ids, location_name=None):
        return [inventory_data[iid] for iid in item_ids if iid in inventory_data]

    service._get_inventory = mock_inventory

    result = await service.get_batch_production_analysis([("FG-100", 5)])

    fg = result["results"][0]
    print(f"  FG-100 desired=5, max_producible={fg['max_quantity_producible']}, status={fg['status']}")

    assert fg["max_quantity_producible"] == 5, (
        f"Expected 5 (on_hand 3 + producible 8 for SA-50 → effective 11, floor(11/2)=5), "
        f"got {fg['max_quantity_producible']}"
    )
    assert fg["can_produce"] is True
    assert fg["status"] == "fully_producible"

    print("  PASS: sub-assembly batch feasibility")


# ============================================================================
# 5. Shared ledger deduction with sub-assemblies
# ============================================================================

async def test_sub_assembly_shared_ledger_deduction():
    """
    Two SKUs sharing raw materials through a sub-assembly.
    SKU-A consumes SA, which deducts raw materials.
    SKU-B (using the same raw material directly) sees reduced availability.

    BOM for SKU-A:
      Level 0: SA-50 (sub-assembly) x1
      Level 1:   RM-10 x2 per SA-50

    BOM for SKU-B:
      Level 0: RM-10 x3

    Inventory: SA-50=1, RM-10=10

    Processing SKU-A (desired=5):
      SA-50 effective = 1 + floor(10/2) = 1 + 5 = 6
      max from SA-50 = floor(6/1) = 6 → capped at 5 (desired)
      Deduction: consume 5 SA-50 → use 1 on-hand, produce 4 → RM-10: 10 - (2*4) = 2

    Processing SKU-B (desired=5):
      RM-10 available = 2 (after SKU-A's deduction)
      max from RM-10 = floor(2/3) = 0
      → blocked
    """
    service = ProductionService(enable_cache=False)

    sku_to_id = {
        "SKU-A": "ID-A", "SKU-B": "ID-B",
        "SA-50": "ID-SA50", "RM-10": "ID-RM10",
    }

    async def mock_resolve(identifier):
        return sku_to_id.get(identifier)

    service._resolve_identifier = mock_resolve

    async def mock_details(item_id):
        details_map = {
            "ID-A": {"itemid": "SKU-A", "displayname": "Product A", "is_manufacturing": "true"},
            "ID-B": {"itemid": "SKU-B", "displayname": "Product B", "is_manufacturing": "true"},
        }
        return details_map.get(item_id)

    service._get_item_details = mock_details

    async def mock_bom(item_sku):
        if item_sku == "SKU-A":
            return [
                make_bom_entry("SA-50", 1, level=0, displayname="Sub Assy", is_manufacturing="true"),
                make_bom_entry("RM-10", 2, level=1, displayname="Raw Mat"),
            ]
        if item_sku == "SKU-B":
            return [
                make_bom_entry("RM-10", 3, level=0, displayname="Raw Mat"),
            ]
        return []

    service._get_bom = mock_bom

    inventory_data = {
        "ID-SA50": make_inventory_record("ID-SA50", "SA-50", 1),
        "ID-RM10": make_inventory_record("ID-RM10", "RM-10", 10),
    }

    async def mock_inventory(item_ids, location_name=None):
        return [inventory_data[iid] for iid in item_ids if iid in inventory_data]

    service._get_inventory = mock_inventory

    result = await service.get_batch_production_analysis([("SKU-A", 5), ("SKU-B", 5)])

    a = result["results"][0]
    b = result["results"][1]

    print(f"  SKU-A: max={a['max_quantity_producible']}, status={a['status']}")
    print(f"  SKU-B: max={b['max_quantity_producible']}, status={b['status']}")

    # max_quantity_producible = 6 (SA effective=6, floor(6/1)=6), but desired=5 so can_produce=True
    assert a["max_quantity_producible"] == 6, f"SKU-A expected 6, got {a['max_quantity_producible']}"
    assert a["can_produce"] is True
    assert a["status"] == "fully_producible"

    # Deduction uses actual_qty=min(6,5)=5:
    # SA-50: from_on_hand=min(5,1)=1, produce=ceil(5-1)=4 → RM-10: 10-(2*4)=2
    assert b["max_quantity_producible"] == 0, f"SKU-B expected 0, got {b['max_quantity_producible']}"
    assert b["status"] == "blocked"

    print("  PASS: shared ledger deduction with sub-assemblies")


# ============================================================================
# 6. Shortage enrichment for sub-assemblies
# ============================================================================

async def test_sub_assembly_shortage_enrichment():
    """
    When a sub-assembly is short, shortage data should include sub_component_details.
    """
    service = ProductionService(enable_cache=False)

    sku_to_id = {"FG": "ID-FG", "SA": "ID-SA", "RM": "ID-RM"}

    async def mock_resolve(identifier):
        return sku_to_id.get(identifier)

    service._resolve_identifier = mock_resolve

    async def mock_details(item_id):
        if item_id == "ID-FG":
            return {"itemid": "FG", "displayname": "Finished", "is_manufacturing": "true"}
        return None

    service._get_item_details = mock_details

    async def mock_bom(item_sku):
        if item_sku == "FG":
            return [
                make_bom_entry("SA", 10, level=0, displayname="SubAssy", is_manufacturing="true"),
                make_bom_entry("RM", 5, level=1, displayname="RawMat"),
            ]
        return []

    service._get_bom = mock_bom

    inventory_data = {
        "ID-SA": make_inventory_record("ID-SA", "SA", 0),
        "ID-RM": make_inventory_record("ID-RM", "RM", 10),
    }

    async def mock_inventory(item_ids, location_name=None):
        return [inventory_data[iid] for iid in item_ids if iid in inventory_data]

    service._get_inventory = mock_inventory

    # Desire 5 FG → need 50 SA, but effective = 0 + floor(10/5) = 2
    result = await service.get_batch_production_analysis([("FG", 5)])
    fg = result["results"][0]

    print(f"  FG: max={fg['max_quantity_producible']}, shortages={len(fg['shortages'])}")

    # max from SA = floor(2/10) = 0
    assert fg["max_quantity_producible"] == 0
    assert len(fg["shortages"]) > 0

    # Check that shortage includes sub_component_details
    sa_shortage = next((s for s in fg["shortages"] if s["item_sku"] == "SA"), None)
    assert sa_shortage is not None, "Expected shortage entry for SA"
    assert "sub_component_details" in sa_shortage, "Expected sub_component_details in shortage"
    assert sa_shortage["sub_component_details"][0]["item_id"] == "ID-RM"

    print("  PASS: shortage enrichment for sub-assemblies")


# ============================================================================
# 7. Contention detection with sub-assembly effective availability
# ============================================================================

async def test_contention_uses_effective_availability():
    """
    Contention detection should use effective availability (on-hand + producible)
    for sub-assembly components, not just raw on-hand.
    """
    service = ProductionService(enable_cache=False)

    sku_to_id = {
        "FG-A": "ID-A", "FG-B": "ID-B",
        "SA": "ID-SA", "RM": "ID-RM",
    }

    async def mock_resolve(identifier):
        return sku_to_id.get(identifier)

    service._resolve_identifier = mock_resolve

    async def mock_details(item_id):
        details = {
            "ID-A": {"itemid": "FG-A", "displayname": "Product A", "is_manufacturing": "true"},
            "ID-B": {"itemid": "FG-B", "displayname": "Product B", "is_manufacturing": "true"},
        }
        return details.get(item_id)

    service._get_item_details = mock_details

    async def mock_bom(item_sku):
        # Both products use SA x1
        if item_sku in ("FG-A", "FG-B"):
            return [
                make_bom_entry("SA", 1, level=0, displayname="SubAssy", is_manufacturing="true"),
                make_bom_entry("RM", 2, level=1, displayname="RawMat"),
            ]
        return []

    service._get_bom = mock_bom

    # SA on-hand=0, RM=20 → SA effective = 0 + floor(20/2) = 10
    # Both products need SA x1, total demand for 5+5 = 10
    # Effective = 10, so NO contention expected
    inventory_data = {
        "ID-SA": make_inventory_record("ID-SA", "SA", 0),
        "ID-RM": make_inventory_record("ID-RM", "RM", 20),
    }

    async def mock_inventory(item_ids, location_name=None):
        return [inventory_data[iid] for iid in item_ids if iid in inventory_data]

    service._get_inventory = mock_inventory

    result = await service.get_batch_production_analysis([("FG-A", 5), ("FG-B", 5)])

    contentions = result["material_contentions"]
    # With effective availability of 10 and total demand of 10, no contention
    sa_contention = [c for c in contentions if c.get("component_sku") == "SA"]
    print(f"  Contentions for SA: {len(sa_contention)} (expected 0)")
    assert len(sa_contention) == 0, (
        f"SA effective=10, demand=10, should not be contention. Got: {sa_contention}"
    )

    print("  PASS: contention uses effective availability")


# ============================================================================
# RUNNER
# ============================================================================

async def main():
    print("\n" + "=" * 70)
    print("BATCH FEASIBILITY TEST SUITE")
    print("=" * 70)

    tests = [
        ("CacheManager get_many/set_many", test_get_many_set_many),
        ("make_single_inventory_cache_key", test_single_cache_key),
        ("Per-component inventory caching", test_per_component_inventory_cache),
        ("Sub-assembly batch feasibility", test_sub_assembly_batch_feasibility),
        ("Shared ledger deduction with sub-assemblies", test_sub_assembly_shared_ledger_deduction),
        ("Sub-assembly shortage enrichment", test_sub_assembly_shortage_enrichment),
        ("Contention with effective availability", test_contention_uses_effective_availability),
    ]

    passed = 0
    failed = 0

    for name, test_fn in tests:
        print(f"\n--- {name} ---")
        try:
            await test_fn()
            passed += 1
        except AssertionError as e:
            print(f"  FAIL: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 70)
    print(f"RESULTS: {passed} passed, {failed} failed out of {len(tests)}")
    print("=" * 70)

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
