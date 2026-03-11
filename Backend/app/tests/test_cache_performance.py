"""
Debug script to test if caching is actually working.
Run this to see cache hits/misses and timing.

Usage from project root:
    python -m app.tests.test_cache_performance
    
Or with pytest:
    pytest app/tests/test_cache_performance.py -v -s
"""
import asyncio
import time
import logging
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app.services.production_service import ProductionService

# Enable detailed logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def test_cache_performance():
    """Test cache performance with same SKU analyzed twice"""
    
    print("\n" + "="*70)
    print("MAIN TEST: CACHE PERFORMANCE WITH SAME SERVICE INSTANCE")
    print("="*70)
    
    # IMPORTANT: Reuse the same service instance!
    service = ProductionService(enable_cache=True)
    
    # Pick a SKU to test (replace with your actual SKU)
    test_sku = "ST61533"  # ← Using the SKU from logs
    test_qty = 1
    
    print(f"\nTest Item: {test_sku}")
    print(f"Test Quantity: {test_qty}")
    print("\n⚠️  IMPORTANT: Using SAME service instance for both calls")
    
    # ========================================
    # FIRST ANALYSIS - Should be SLOW (cache miss)
    # ========================================
    print("\n" + "-"*70)
    print("FIRST ANALYSIS (Cold Cache - Expected: SLOW ~8s)")
    print("-"*70)
    
    start_time = time.time()
    result1 = await service.get_production_analysis(test_sku, test_qty)
    elapsed1 = time.time() - start_time
    
    print(f"✓ First analysis completed in: {elapsed1:.3f}s")
    print(f"  Can produce: {result1.get('can_produce')}")
    print(f"  Max quantity: {result1.get('max_quantity_producible')}")
    
    # Check cache stats after first run
    print("\n--- Cache Stats After First Run ---")
    stats1 = service.get_cache_stats()
    print(f"BOM cache - Hits: {stats1['bom']['hits']}, Misses: {stats1['bom']['misses']}")
    print(f"Item Details - Hits: {stats1['item_details']['hits']}, Misses: {stats1['item_details']['misses']}")
    print(f"Resolution - Hits: {stats1['resolution']['hits']}, Misses: {stats1['resolution']['misses']}")
    print(f"Total cached items: {stats1['cache_size']}")
    
    if stats1['cache_size'] == 0:
        print("\n❌ ERROR: Nothing was cached! Check if caching is enabled.")
        return
    
    # ========================================
    # SECOND ANALYSIS - Should be FAST (cache hit)
    # ========================================
    print("\n" + "-"*70)
    print("SECOND ANALYSIS (Warm Cache - Expected: FAST ~4s)")
    print("-"*70)
    print("⚠️  Using SAME service instance - cache should be preserved!")
    
    # Small delay to make it realistic
    await asyncio.sleep(1)
    
    start_time = time.time()
    result2 = await service.get_production_analysis(test_sku, test_qty)
    elapsed2 = time.time() - start_time
    
    print(f"✓ Second analysis completed in: {elapsed2:.3f}s")
    print(f"  Can produce: {result2.get('can_produce')}")
    print(f"  Max quantity: {result2.get('max_quantity_producible')}")
    
    # Check cache stats after second run
    print("\n--- Cache Stats After Second Run ---")
    stats2 = service.get_cache_stats()
    print(f"BOM cache - Hits: {stats2['bom']['hits']}, Misses: {stats2['bom']['misses']}")
    print(f"Item Details - Hits: {stats2['item_details']['hits']}, Misses: {stats2['item_details']['misses']}")
    print(f"Resolution - Hits: {stats2['resolution']['hits']}, Misses: {stats2['resolution']['misses']}")
    print(f"Total cached items: {stats2['cache_size']}")
    
    # ========================================
    # ANALYSIS
    # ========================================
    print("\n" + "="*70)
    print("PERFORMANCE ANALYSIS")
    print("="*70)
    
    speedup = ((elapsed1 - elapsed2) / elapsed1) * 100 if elapsed1 > 0 else 0
    time_saved = elapsed1 - elapsed2
    
    print(f"\nFirst run time:  {elapsed1:.3f}s (cache miss)")
    print(f"Second run time: {elapsed2:.3f}s (cache hit)")
    print(f"Time saved:      {time_saved:.3f}s")
    print(f"Speedup:         {speedup:.1f}%")
    
    # Calculate BOM-specific stats
    bom_hits = stats2['bom']['hits'] - stats1['bom']['hits']
    bom_misses_first = stats1['bom']['misses']
    
    print(f"\nBOM fetches in first run:  {bom_misses_first} (all cache misses)")
    print(f"BOM fetches in second run: {bom_hits} (cache hits!)")
    
    # Diagnosis
    print("\n--- DIAGNOSIS ---")
    
    if stats2['cache_size'] == 0:
        print("❌ PROBLEM: Cache is empty! No data was cached.")
        print("   Possible causes:")
        print("   - Cache is disabled")
        print("   - Service instance was recreated")
    elif bom_hits == 0:
        print("❌ PROBLEM: No BOM cache hits detected!")
        print("   The cache was set but never retrieved.")
        print("   Check the get_full_bom cache logic.")
    elif time_saved < 2.0:
        print("⚠️  WARNING: Time saved is less than 2 seconds.")
        print(f"   Inventory fetching likely dominates ({elapsed2:.1f}s)")
        print("   This is normal - inventory is always fetched fresh.")
    else:
        print("✅ SUCCESS: Caching is working!")
        print(f"   Second run was {speedup:.1f}% faster")
        print(f"   Saved {time_saved:.1f} seconds on BOM fetches")
        print(f"   Cache prevented {bom_hits} BOM API calls")
    
    # Show detailed cache stats
    print("\n--- DETAILED CACHE STATISTICS ---")
    service.print_cache_stats()
    
    return {
        'first_run_time': elapsed1,
        'second_run_time': elapsed2,
        'speedup_percent': speedup,
        'cache_stats': stats2,
        'bom_hits': bom_hits
    }


async def test_without_cache():
    """Test performance WITHOUT caching for comparison"""
    
    print("\n" + "="*70)
    print("CONTROL TEST - WITHOUT CACHING")
    print("="*70)
    
    test_sku = "ST61533"  # ← CHANGE THIS
    test_qty = 1
    
    # Run with caching disabled
    service = ProductionService(enable_cache=False)
    
    print("\n--- First Run (No Cache) ---")
    start_time = time.time()
    result1 = await service.get_production_analysis(test_sku, test_qty)
    elapsed1 = time.time() - start_time
    print(f"Time: {elapsed1:.3f}s")
    
    await asyncio.sleep(1)
    
    print("\n--- Second Run (No Cache) ---")
    start_time = time.time()
    result2 = await service.get_production_analysis(test_sku, test_qty)
    elapsed2 = time.time() - start_time
    print(f"Time: {elapsed2:.3f}s")
    
    print(f"\nBoth runs took similar time: {elapsed1:.3f}s vs {elapsed2:.3f}s")
    print("This is expected without caching.\n")


async def test_new_instance_problem():
    """Demonstrate the problem of creating new instances"""
    
    print("\n" + "="*70)
    print("ANTI-PATTERN TEST - New Instance Each Time")
    print("="*70)
    print("This shows why creating new service instances breaks caching\n")
    
    test_sku = "ST61533"  # ← CHANGE THIS
    test_qty = 1
    
    # BAD: New instance each time
    print("--- Run 1 (New Instance) ---")
    service1 = ProductionService(enable_cache=True)
    start_time = time.time()
    await service1.get_production_analysis(test_sku, test_qty)
    elapsed1 = time.time() - start_time
    print(f"Time: {elapsed1:.3f}s")
    stats1 = service1.get_cache_stats()
    print(f"Cache size: {stats1['cache_size']}")
    
    # BAD: Another new instance - cache is lost!
    print("\n--- Run 2 (New Instance - Cache Lost!) ---")
    service2 = ProductionService(enable_cache=True)  # ← New instance = empty cache!
    start_time = time.time()
    await service2.get_production_analysis(test_sku, test_qty)
    elapsed2 = time.time() - start_time
    print(f"Time: {elapsed2:.3f}s")
    stats2 = service2.get_cache_stats()
    print(f"Cache size: {stats2['cache_size']} (previous cache was lost)")
    
    print("\n❌ PROBLEM: Both runs took similar time because cache was lost!")
    print("✓ SOLUTION: Reuse the same service instance")


async def main():
    """Run all tests"""
    
    print("\n" + "="*70)
    print("CACHE DEBUG TEST SUITE")
    print("="*70)
    
    try:
        # Main test - THIS IS THE IMPORTANT ONE
        result = await test_cache_performance()
        
        if result and result.get('bom_hits', 0) > 0:
            print("\n" + "="*70)
            print("🎉 SUCCESS! Caching is working properly!")
            print("="*70)
        else:
            print("\n" + "="*70)
            print("⚠️  Cache may not be working as expected.")
            print("="*70)
        
        # Uncomment these if you want to run additional tests
        # await test_without_cache()
        # await test_new_instance_problem()
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())