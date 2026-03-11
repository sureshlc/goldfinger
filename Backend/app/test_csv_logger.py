"""
Test script for CSV Logger Service
Run this to validate csv_logger.py functionality

Usage:
    python test_csv_logger.py
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
import time

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

from app.utils.csv_logger import get_csv_logger, log_user, log_session, log_request, log_requests_batch


def print_section(title):
    """Print formatted section header"""
    print("\n" + "="*70)
    print(f"  {title}")
    print("="*70)


def test_1_initialization():
    """Test 1: CSV Logger Initialization"""
    print_section("TEST 1: Initialization")
    
    try:
        logger = get_csv_logger()
        print("✅ CSV Logger instance created")
        
        # Check if logs directory exists
        logs_dir = Path("logs")
        if logs_dir.exists():
            print(f"✅ Logs directory exists: {logs_dir.absolute()}")
        else:
            print("❌ Logs directory not created")
            return False
        
        # Check if CSV files exist
        files = ["users.csv", "sessions.csv", "requests.csv"]
        for filename in files:
            filepath = logs_dir / filename
            if filepath.exists():
                print(f"✅ {filename} created")
                # Check if file has headers
                with open(filepath, 'r') as f:
                    first_line = f.readline().strip()
                    if first_line:
                        print(f"   Headers: {first_line[:80]}...")
            else:
                print(f"❌ {filename} not created")
                return False
        
        print("\n✅ TEST 1 PASSED: All files initialized correctly")
        return True
        
    except Exception as e:
        print(f"❌ TEST 1 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_2_log_user():
    """Test 2: Logging User Data"""
    print_section("TEST 2: Log User Data")
    
    try:
        logger = get_csv_logger()
        
        # Test user 1
        user1 = {
            "user_id": "123",
            "username": "john_doe",
            "email": "john@company.com",
            "created_at": datetime.utcnow().isoformat(),
            "last_login": datetime.utcnow().isoformat()
        }
        
        result = logger.append_user(user1)
        if result:
            print(f"✅ User 1 logged: {user1['username']}")
        else:
            print("❌ Failed to log user 1")
            return False
        
        # Test user 2
        user2 = {
            "user_id": "456",
            "username": "jane_smith",
            "email": "jane@company.com",
            "created_at": datetime.utcnow().isoformat(),
            "last_login": datetime.utcnow().isoformat()
        }
        
        result = logger.append_user(user2)
        if result:
            print(f"✅ User 2 logged: {user2['username']}")
        else:
            print("❌ Failed to log user 2")
            return False
        
        # Verify users.csv
        users_file = Path("logs/users.csv")
        with open(users_file, 'r') as f:
            lines = f.readlines()
            print(f"\n📄 users.csv content ({len(lines)} lines):")
            for i, line in enumerate(lines[:5], 1):  # Show first 5 lines
                print(f"   {i}. {line.strip()}")
        
        if len(lines) >= 3:  # Header + 2 users
            print("\n✅ TEST 2 PASSED: Users logged successfully")
            return True
        else:
            print(f"\n❌ TEST 2 FAILED: Expected 3 lines, got {len(lines)}")
            return False
            
    except Exception as e:
        print(f"❌ TEST 2 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_3_log_session():
    """Test 3: Logging Session Data"""
    print_section("TEST 3: Log Session Data")
    
    try:
        logger = get_csv_logger()
        
        # Active session
        session1 = {
            "session_id": "sess-abc-123",
            "user_id": "123",
            "login_time": datetime.utcnow().isoformat(),
            "logout_time": None,
            "session_duration_mins": None,
            "total_requests": 0,
            "status": "active"
        }
        
        result = logger.append_session(session1)
        if result:
            print(f"✅ Active session logged: {session1['session_id']}")
        else:
            print("❌ Failed to log active session")
            return False
        
        # Simulate some time passing
        time.sleep(0.1)
        
        # Completed session
        login_time = datetime.utcnow() - timedelta(minutes=45)
        logout_time = datetime.utcnow()
        duration = (logout_time - login_time).total_seconds() / 60
        
        session2 = {
            "session_id": "sess-def-456",
            "user_id": "456",
            "login_time": login_time.isoformat(),
            "logout_time": logout_time.isoformat(),
            "session_duration_mins": round(duration, 2),
            "total_requests": 15,
            "status": "completed"
        }
        
        result = logger.append_session(session2)
        if result:
            print(f"✅ Completed session logged: {session2['session_id']}")
        else:
            print("❌ Failed to log completed session")
            return False
        
        # Verify sessions.csv
        sessions_file = Path("logs/sessions.csv")
        with open(sessions_file, 'r') as f:
            lines = f.readlines()
            print(f"\n📄 sessions.csv content ({len(lines)} lines):")
            for i, line in enumerate(lines[:5], 1):
                print(f"   {i}. {line.strip()}")
        
        if len(lines) >= 3:  # Header + 2 sessions
            print("\n✅ TEST 3 PASSED: Sessions logged successfully")
            return True
        else:
            print(f"\n❌ TEST 3 FAILED: Expected 3 lines, got {len(lines)}")
            return False
            
    except Exception as e:
        print(f"❌ TEST 3 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_4_log_request():
    """Test 4: Logging Request Data"""
    print_section("TEST 4: Log Request Data")
    
    try:
        logger = get_csv_logger()
        
        # Successful request
        request1 = {
            "timestamp": datetime.utcnow().isoformat(),
            "request_id": "req-001",
            "session_id": "sess-abc-123",
            "user_id": "123",
            "endpoint": "/api/production/feasibility",
            "item_sku": "12342",
            "desired_quantity": 100,
            "max_producible": 1014,
            "can_produce": True,
            "limiting_component": "Component B",
            "shortages_count": 3,
            "response_time_ms": 3200,
            "status_code": 200,
            "error_type": None,
            "error_message": None,
            "cache_hit": True,
            "location": "Main Warehouse"
        }
        
        result = logger.append_request(request1)
        if result:
            print(f"✅ Successful request logged: {request1['request_id']}")
        else:
            print("❌ Failed to log successful request")
            return False
        
        # Failed request
        request2 = {
            "timestamp": datetime.utcnow().isoformat(),
            "request_id": "req-002",
            "session_id": "sess-abc-123",
            "user_id": "123",
            "endpoint": "/api/production/feasibility",
            "item_sku": "99999",
            "desired_quantity": 50,
            "max_producible": None,
            "can_produce": None,
            "limiting_component": None,
            "shortages_count": None,
            "response_time_ms": 1200,
            "status_code": 404,
            "error_type": "not_found",
            "error_message": "Item with SKU 99999 not found",
            "cache_hit": None,
            "location": None
        }
        
        result = logger.append_request(request2)
        if result:
            print(f"✅ Failed request logged: {request2['request_id']}")
        else:
            print("❌ Failed to log failed request")
            return False
        
        # Verify requests.csv
        requests_file = Path("logs/requests.csv")
        with open(requests_file, 'r') as f:
            lines = f.readlines()
            print(f"\n📄 requests.csv content ({len(lines)} lines):")
            for i, line in enumerate(lines[:5], 1):
                print(f"   {i}. {line.strip()[:100]}...")
        
        if len(lines) >= 3:  # Header + 2 requests
            print("\n✅ TEST 4 PASSED: Requests logged successfully")
            return True
        else:
            print(f"\n❌ TEST 4 FAILED: Expected 3 lines, got {len(lines)}")
            return False
            
    except Exception as e:
        print(f"❌ TEST 4 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_5_batch_logging():
    """Test 5: Batch Request Logging"""
    print_section("TEST 5: Batch Request Logging")
    
    try:
        logger = get_csv_logger()
        
        # Create batch of 5 requests
        batch_requests = []
        for i in range(5):
            request = {
                "timestamp": datetime.utcnow().isoformat(),
                "request_id": f"req-batch-{i+1}",
                "session_id": "sess-abc-123",
                "user_id": "123",
                "endpoint": "/api/production/capacity",
                "item_sku": f"SKU-{1000+i}",
                "desired_quantity": 10 * (i+1),
                "max_producible": 50 * (i+1),
                "can_produce": True,
                "limiting_component": "Component X",
                "shortages_count": 0,
                "response_time_ms": 2000 + (i * 100),
                "status_code": 200,
                "error_type": None,
                "error_message": None,
                "cache_hit": i % 2 == 0,  # Alternate cache hits
                "location": "Warehouse A"
            }
            batch_requests.append(request)
        
        count = logger.batch_append_requests(batch_requests)
        
        if count == 5:
            print(f"✅ Batch logged {count} requests successfully")
        else:
            print(f"❌ Expected 5 requests, only logged {count}")
            return False
        
        # Verify requests.csv has all records
        requests_file = Path("logs/requests.csv")
        with open(requests_file, 'r') as f:
            lines = f.readlines()
            print(f"\n📄 requests.csv now has {len(lines)} lines total")
        
        print("\n✅ TEST 5 PASSED: Batch logging works correctly")
        return True
            
    except Exception as e:
        print(f"❌ TEST 5 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_6_convenience_functions():
    """Test 6: Convenience Functions"""
    print_section("TEST 6: Convenience Functions")
    
    try:
        # Test convenience functions
        user_result = log_user({
            "user_id": "789",
            "username": "convenience_test",
            "email": "test@company.com",
            "created_at": datetime.utcnow().isoformat(),
            "last_login": datetime.utcnow().isoformat()
        })
        
        session_result = log_session({
            "session_id": "sess-conv-123",
            "user_id": "789",
            "login_time": datetime.utcnow().isoformat(),
            "logout_time": None,
            "session_duration_mins": None,
            "total_requests": 0,
            "status": "active"
        })
        
        request_result = log_request({
            "timestamp": datetime.utcnow().isoformat(),
            "request_id": "req-conv-001",
            "session_id": "sess-conv-123",
            "user_id": "789",
            "endpoint": "/api/production/shortages",
            "item_sku": "TEST-SKU",
            "desired_quantity": 25,
            "max_producible": 100,
            "can_produce": True,
            "limiting_component": None,
            "shortages_count": 0,
            "response_time_ms": 1500,
            "status_code": 200,
            "error_type": None,
            "error_message": None,
            "cache_hit": False,
            "location": None
        })
        
        if user_result and session_result and request_result:
            print("✅ All convenience functions work")
            print("   - log_user() ✅")
            print("   - log_session() ✅")
            print("   - log_request() ✅")
            print("\n✅ TEST 6 PASSED: Convenience functions work correctly")
            return True
        else:
            print("❌ Some convenience functions failed")
            return False
            
    except Exception as e:
        print(f"❌ TEST 6 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_7_get_stats():
    """Test 7: Get Statistics"""
    print_section("TEST 7: Get Statistics")
    
    try:
        logger = get_csv_logger()
        stats = logger.get_stats()
        
        print("📊 CSV Logger Statistics:")
        print(f"   Users count: {stats.get('users_count')}")
        print(f"   Sessions count: {stats.get('sessions_count')}")
        print(f"   Requests count: {stats.get('requests_count')}")
        print(f"\n   Users file: {stats.get('users_file')}")
        print(f"   Sessions file: {stats.get('sessions_file')}")
        print(f"   Requests file: {stats.get('requests_file')}")
        
        if stats.get('users_count', 0) > 0 and stats.get('requests_count', 0) > 0:
            print("\n✅ TEST 7 PASSED: Statistics retrieved successfully")
            return True
        else:
            print("\n❌ TEST 7 FAILED: No data in statistics")
            return False
            
    except Exception as e:
        print(f"❌ TEST 7 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("\n" + "="*70)
    print("  CSV LOGGER TEST SUITE")
    print("="*70)
    print(f"  Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    
    results = []
    
    # Run all tests
    results.append(("Initialization", test_1_initialization()))
    results.append(("Log User", test_2_log_user()))
    results.append(("Log Session", test_3_log_session()))
    results.append(("Log Request", test_4_log_request()))
    results.append(("Batch Logging", test_5_batch_logging()))
    results.append(("Convenience Functions", test_6_convenience_functions()))
    results.append(("Get Statistics", test_7_get_stats()))
    
    # Summary
    print_section("TEST SUMMARY")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}  {test_name}")
    
    print(f"\n{'='*70}")
    print(f"  Total: {passed}/{total} tests passed")
    
    if passed == total:
        print(f"  🎉 ALL TESTS PASSED! 🎉")
    else:
        print(f"  ⚠️  {total - passed} test(s) failed")
    
    print(f"  Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)