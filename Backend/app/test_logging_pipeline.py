"""
Comprehensive Test Suite for Logging Pipeline
Tests CSV Logger, Session Service, Background Writer, and Middleware integration

Run with: python -m app.test_logging_pipeline
"""
import asyncio
import sys
import os
import time
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.utils.csv_logger import get_csv_logger, CSVLogger
from app.services.session_service import SessionService, init_session_service
from app.background.csv_writer import (
    init_log_queue, 
    start_csv_writer, 
    stop_csv_writer,
    log_user_async,
    log_session_async,
    log_request_async,
    get_queue_stats
)


def print_header(title: str):
    """Print formatted test header"""
    print("\n" + "="*70)
    print(f"  {title}")
    print("="*70)


def print_test_result(test_name: str, passed: bool, message: str = ""):
    """Print test result"""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status}  {test_name}")
    if message:
        print(f"   {message}")


async def test_1_csv_logger_initialization():
    """Test 1: CSV Logger initialization and file creation"""
    print_header("TEST 1: CSV Logger Initialization")
    
    try:
        # Initialize CSV logger
        csv_logger = get_csv_logger()
        
        # Check if log files exist
        log_dir = Path("logs")
        users_csv = log_dir / "users.csv"
        sessions_csv = log_dir / "sessions.csv"
        requests_csv = log_dir / "requests.csv"
        
        files_exist = (
            users_csv.exists() and 
            sessions_csv.exists() and 
            requests_csv.exists()
        )
        
        print(f"📁 Log directory: {log_dir.absolute()}")
        print(f"   users.csv: {'✓' if users_csv.exists() else '✗'}")
        print(f"   sessions.csv: {'✓' if sessions_csv.exists() else '✗'}")
        print(f"   requests.csv: {'✓' if requests_csv.exists() else '✗'}")
        
        # Get stats
        stats = csv_logger.get_stats()
        print(f"\n📊 CSV Statistics:")
        print(f"   Users: {stats.get('users_count', 0)}")
        print(f"   Sessions: {stats.get('sessions_count', 0)}")
        print(f"   Requests: {stats.get('requests_count', 0)}")
        
        print_test_result("CSV Logger Initialization", files_exist)
        return files_exist
        
    except Exception as e:
        print(f"❌ Error: {e}")
        print_test_result("CSV Logger Initialization", False, str(e))
        return False


async def test_2_session_service():
    """Test 2: Session Service functionality"""
    print_header("TEST 2: Session Service")
    
    try:
        # Initialize session service
        session_service = init_session_service(session_timeout_minutes=30)
        
        # Create test session
        session = session_service.create_session(
            user_id="test_user_001",
            username="testuser",
            email="test@example.com"
        )
        
        print(f"📝 Created Session:")
        print(f"   Session ID: {session.session_id}")
        print(f"   User ID: {session.user_id}")
        print(f"   Login Time: {session.login_time}")
        print(f"   Status: {session.status}")
        
        # Increment request count
        session_service.increment_request_count(session.session_id)
        session_service.increment_request_count(session.session_id)
        
        print(f"\n📊 After 2 requests:")
        print(f"   Total Requests: {session.total_requests}")
        
        # Get session stats
        stats = session_service.get_stats()
        print(f"\n📊 Service Statistics:")
        print(f"   Active Sessions: {stats['active_sessions']}")
        print(f"   Users Online: {stats['users_online']}")
        
        success = (
            session.session_id is not None and
            session.total_requests == 2 and
            stats['active_sessions'] == 1
        )
        
        print_test_result("Session Service", success)
        return success, session_service
        
    except Exception as e:
        print(f"❌ Error: {e}")
        print_test_result("Session Service", False, str(e))
        return False, None


async def test_3_background_queue():
    """Test 3: Background queue and worker"""
    print_header("TEST 3: Background Queue & Worker")
    
    try:
        # Initialize queue
        init_log_queue()
        print("✓ Queue initialized")
        
        # Start background worker
        await start_csv_writer()
        print("✓ Background worker started")
        
        # Give worker time to start
        await asyncio.sleep(0.5)
        
        # Check queue stats
        stats = await get_queue_stats()
        print(f"\n📊 Queue Statistics:")
        print(f"   Queue Initialized: {stats['queue_initialized']}")
        print(f"   Queue Size: {stats['queue_size']}")
        print(f"   Max Size: {stats['queue_max_size']}")
        print(f"   Worker Running: {stats['worker_running']}")
        
        success = stats['queue_initialized'] and stats['worker_running']
        print_test_result("Background Queue & Worker", success)
        return success
        
    except Exception as e:
        print(f"❌ Error: {e}")
        print_test_result("Background Queue & Worker", False, str(e))
        return False


async def test_4_async_logging():
    """Test 4: Async logging via queue"""
    print_header("TEST 4: Async Logging via Queue")
    
    try:
        csv_logger = get_csv_logger()
        initial_stats = csv_logger.get_stats()
        
        print(f"📊 Initial counts:")
        print(f"   Users: {initial_stats['users_count']}")
        print(f"   Sessions: {initial_stats['sessions_count']}")
        print(f"   Requests: {initial_stats['requests_count']}")
        
        # Log user event
        user_data = {
            "user_id": "test_user_002",
            "username": "asyncuser",
            "email": "async@example.com",
            "created_at": datetime.utcnow().isoformat() + "Z",
            "last_login": datetime.utcnow().isoformat() + "Z"
        }
        await log_user_async(user_data)
        print("\n✓ Enqueued user log")
        
        # Log session event
        session_data = {
            "session_id": "999",
            "user_id": "test_user_002",
            "login_time": datetime.utcnow().isoformat() + "Z",
            "logout_time": None,
            "session_duration_mins": None,
            "total_requests": 0,
            "status": "active"
        }
        await log_session_async(session_data)
        print("✓ Enqueued session log")
        
        # Log multiple request events
        for i in range(5):
            request_data = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "request_id": f"req_{i+1}",
                "session_id": "999",
                "user_id": "test_user_002",
                "endpoint": "/api/test",
                "item_sku": f"ITEM-{i+1:03d}",
                "desired_quantity": str((i+1) * 10),
                "max_producible": str((i+1) * 8),
                "can_produce": "true" if i % 2 == 0 else "false",
                "limiting_component": f"COMP-{i+1}" if i % 2 == 1 else "",
                "shortages_count": str(i) if i % 2 == 1 else "0",
                "response_time_ms": str(100 + i * 10),
                "status_code": "200",
                "error_type": "",
                "error_message": "",
                "cache_hit": "true" if i % 2 == 0 else "false",
                "location": ""
            }
            await log_request_async(request_data)
        
        print(f"✓ Enqueued 5 request logs")
        
        # Check queue stats
        stats = await get_queue_stats()
        print(f"\n📊 Queue after enqueuing:")
        print(f"   Queue Size: {stats['queue_size']}")
        
        # Wait for background worker to process
        print("\n⏳ Waiting for background worker to process (6 seconds)...")
        await asyncio.sleep(6)
        
        # Check final stats
        final_stats = csv_logger.get_stats()
        print(f"\n📊 Final counts:")
        print(f"   Users: {final_stats['users_count']} (expected: {initial_stats['users_count'] + 1})")
        print(f"   Sessions: {final_stats['sessions_count']} (expected: {initial_stats['sessions_count'] + 1})")
        print(f"   Requests: {final_stats['requests_count']} (expected: {initial_stats['requests_count'] + 5})")
        
        # Verify counts increased
        users_increased = final_stats['users_count'] > initial_stats['users_count']
        sessions_increased = final_stats['sessions_count'] > initial_stats['sessions_count']
        requests_increased = final_stats['requests_count'] >= initial_stats['requests_count'] + 5
        
        success = users_increased and sessions_increased and requests_increased
        
        print_test_result("Async Logging via Queue", success)
        return success
        
    except Exception as e:
        print(f"❌ Error: {e}")
        print_test_result("Async Logging via Queue", False, str(e))
        return False


async def test_5_batch_processing():
    """Test 5: Batch processing efficiency"""
    print_header("TEST 5: Batch Processing")
    
    try:
        csv_logger = get_csv_logger()
        initial_count = csv_logger.get_stats()['requests_count']
        
        print(f"📊 Initial request count: {initial_count}")
        
        # Enqueue 100 requests rapidly
        start_time = time.time()
        for i in range(100):
            request_data = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "request_id": f"batch_req_{i+1}",
                "session_id": "batch_session",
                "user_id": "batch_user",
                "endpoint": "/api/batch",
                "item_sku": f"BATCH-{i+1:03d}",
                "desired_quantity": "10",
                "max_producible": "10",
                "can_produce": "true",
                "limiting_component": "",
                "shortages_count": "0",
                "response_time_ms": "50",
                "status_code": "200",
                "error_type": "",
                "error_message": "",
                "cache_hit": "false",
                "location": ""
            }
            await log_request_async(request_data)
        
        enqueue_time = (time.time() - start_time) * 1000
        print(f"\n⚡ Enqueued 100 requests in {enqueue_time:.2f}ms")
        print(f"   Average: {enqueue_time/100:.2f}ms per request")
        
        # Wait for processing
        print("\n⏳ Waiting for batch processing (8 seconds)...")
        await asyncio.sleep(8)
        
        # Check final count
        final_count = csv_logger.get_stats()['requests_count']
        processed = final_count - initial_count
        
        print(f"\n📊 Processing complete:")
        print(f"   Initial: {initial_count}")
        print(f"   Final: {final_count}")
        print(f"   Processed: {processed}")
        
        success = processed >= 100
        print_test_result("Batch Processing", success, 
                         f"Processed {processed}/100 requests")
        return success
        
    except Exception as e:
        print(f"❌ Error: {e}")
        print_test_result("Batch Processing", False, str(e))
        return False


async def test_6_graceful_shutdown():
    """Test 6: Graceful shutdown and queue flush"""
    print_header("TEST 6: Graceful Shutdown")
    
    try:
        # Get stats before shutdown
        csv_logger = get_csv_logger()
        before_shutdown = csv_logger.get_stats()['requests_count']
        
        # Enqueue some final requests
        for i in range(10):
            request_data = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "request_id": f"shutdown_req_{i+1}",
                "session_id": "shutdown_session",
                "user_id": "shutdown_user",
                "endpoint": "/api/shutdown",
                "item_sku": f"SHUT-{i+1:03d}",
                "desired_quantity": "1",
                "max_producible": "1",
                "can_produce": "true",
                "limiting_component": "",
                "shortages_count": "0",
                "response_time_ms": "25",
                "status_code": "200",
                "error_type": "",
                "error_message": "",
                "cache_hit": "false",
                "location": ""
            }
            await log_request_async(request_data)
        
        print("✓ Enqueued 10 final requests")
        
        # Check queue before shutdown
        queue_stats = await get_queue_stats()
        print(f"📊 Queue before shutdown: {queue_stats['queue_size']} items")
        
        # Stop worker (should flush queue)
        print("\n⏳ Stopping background worker...")
        await stop_csv_writer()
        print("✓ Worker stopped")
        
        # Check final count
        after_shutdown = csv_logger.get_stats()['requests_count']
        flushed = after_shutdown - before_shutdown
        
        print(f"\n📊 Shutdown statistics:")
        print(f"   Before: {before_shutdown}")
        print(f"   After: {after_shutdown}")
        print(f"   Flushed: {flushed}")
        
        success = flushed >= 10
        print_test_result("Graceful Shutdown", success,
                         f"Flushed {flushed}/10 pending requests")
        return success
        
    except Exception as e:
        print(f"❌ Error: {e}")
        print_test_result("Graceful Shutdown", False, str(e))
        return False


async def test_7_error_handling():
    """Test 7: Error handling and logging"""
    print_header("TEST 7: Error Handling")
    
    try:
        # Restart worker for this test
        init_log_queue()
        await start_csv_writer()
        
        csv_logger = get_csv_logger()
        initial_count = csv_logger.get_stats()['requests_count']
        
        # Log request with error
        error_request = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "request_id": "error_req_001",
            "session_id": "error_session",
            "user_id": "error_user",
            "endpoint": "/api/error",
            "item_sku": "ERROR-001",
            "desired_quantity": "100",
            "max_producible": "0",
            "can_produce": "false",
            "limiting_component": "CRITICAL-COMP",
            "shortages_count": "5",
            "response_time_ms": "150",
            "status_code": "500",
            "error_type": "InternalServerError",
            "error_message": "Production capacity exceeded",
            "cache_hit": "false",
            "location": ""
        }
        
        await log_request_async(error_request)
        print("✓ Logged error request")
        
        # Wait for processing
        await asyncio.sleep(6)
        
        # Verify it was logged
        final_count = csv_logger.get_stats()['requests_count']
        error_logged = final_count > initial_count
        
        print(f"\n📊 Error logging:")
        print(f"   Request logged: {'Yes' if error_logged else 'No'}")
        
        # Stop worker
        await stop_csv_writer()
        
        print_test_result("Error Handling", error_logged)
        return error_logged
        
    except Exception as e:
        print(f"❌ Error: {e}")
        print_test_result("Error Handling", False, str(e))
        return False


async def main():
    """Run all tests"""
    print("\n" + "="*70)
    print("  LOGGING PIPELINE TEST SUITE")
    print("="*70)
    print(f"  Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    
    results = []
    
    # Run tests
    results.append(("CSV Logger Initialization", await test_1_csv_logger_initialization()))
    
    test_2_result, session_service = await test_2_session_service()
    results.append(("Session Service", test_2_result))
    
    results.append(("Background Queue & Worker", await test_3_background_queue()))
    results.append(("Async Logging via Queue", await test_4_async_logging()))
    results.append(("Batch Processing", await test_5_batch_processing()))
    results.append(("Graceful Shutdown", await test_6_graceful_shutdown()))
    results.append(("Error Handling", await test_7_error_handling()))
    
    # Print summary
    print_header("TEST SUMMARY")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}  {test_name}")
    
    print("="*70)
    print(f"  Total: {passed}/{total} tests passed")
    
    if passed == total:
        print("  🎉 ALL TESTS PASSED! 🎉")
    else:
        print(f"  ⚠️  {total - passed} test(s) failed")
    
    print("="*70)
    
    # Cleanup
    if session_service:
        session_service.shutdown()
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)