"""
Test script for Session Service
Run this to validate session_service.py functionality

Usage:
    python -m app.test_session_service
"""
import sys
from pathlib import Path
from datetime import datetime
import time

# Add app to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.session_service import SessionService, get_session_service, init_session_service


def print_section(title):
    """Print formatted section header"""
    print("\n" + "="*70)
    print(f"  {title}")
    print("="*70)


def test_1_initialization():
    """Test 1: Session Service Initialization"""
    print_section("TEST 1: Initialization")
    
    try:
        # Initialize with custom timeout
        service = init_session_service(session_timeout_minutes=30)
        
        print("✅ Session Service instance created")
        print(f"   Timeout: 30 minutes")
        
        stats = service.get_stats()
        print(f"\n📊 Initial Statistics:")
        print(f"   Active sessions: {stats['active_sessions']}")
        print(f"   Users online: {stats['users_online']}")
        print(f"   Timeout: {stats['session_timeout_minutes']} minutes")
        
        if stats['active_sessions'] == 0:
            print("\n✅ TEST 1 PASSED: Service initialized correctly")
            return True
        else:
            print("\n❌ TEST 1 FAILED: Expected 0 active sessions")
            return False
            
    except Exception as e:
        print(f"❌ TEST 1 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_2_create_session():
    """Test 2: Create User Session"""
    print_section("TEST 2: Create Session")
    
    try:
        service = get_session_service()
        
        # Create first session
        session1 = service.create_session(
            user_id="1",  # Sequential ID
            username="john_doe",
            email="john@company.com"
        )
        
        print(f"✅ Session created for user 1")
        print(f"   Session ID: {session1.session_id}")
        print(f"   User ID: {session1.user_id}")
        print(f"   Login time: {session1.login_time}")
        print(f"   Status: {session1.status}")
        print(f"   Total requests: {session1.total_requests}")
        
        # Verify session ID is numeric and sequential
        if session1.session_id == "1":
            print(f"   ✅ Session ID is sequential: {session1.session_id}")
        else:
            print(f"   ⚠️  Expected session ID '1', got '{session1.session_id}'")
        
        # Create second session
        session2 = service.create_session(
            user_id="2",  # Sequential ID
            username="jane_smith",
            email="jane@company.com"
        )
        
        print(f"\n✅ Session created for user 2")
        print(f"   Session ID: {session2.session_id}")
        
        # Verify sequential IDs
        if session2.session_id == "2":
            print(f"   ✅ Session ID is sequential: {session2.session_id}")
        else:
            print(f"   ⚠️  Expected session ID '2', got '{session2.session_id}'")
        
        # Check stats
        stats = service.get_stats()
        print(f"\n📊 Statistics after creating 2 sessions:")
        print(f"   Active sessions: {stats['active_sessions']}")
        print(f"   Users online: {stats['users_online']}")
        
        # Verify CSV files
        users_file = Path("logs/users.csv")
        sessions_file = Path("logs/sessions.csv")
        
        if users_file.exists():
            with open(users_file, 'r') as f:
                lines = f.readlines()
                print(f"\n📄 users.csv has {len(lines)} lines")
                if len(lines) >= 3:  # Header + 2 users
                    print("   ✅ Users logged to CSV")
                    for line in lines[-2:]:  # Show last 2 users
                        print(f"   {line.strip()}")
        
        if sessions_file.exists():
            with open(sessions_file, 'r') as f:
                lines = f.readlines()
                print(f"\n📄 sessions.csv has {len(lines)} lines")
                if len(lines) >= 3:  # Header + 2 sessions
                    print("   ✅ Sessions logged to CSV")
                    for line in lines[-2:]:  # Show last 2 sessions
                        print(f"   {line.strip()}")
        
        if stats['active_sessions'] == 2 and stats['users_online'] == 2:
            print("\n✅ TEST 2 PASSED: Sessions created successfully")
            return True
        else:
            print("\n❌ TEST 2 FAILED: Expected 2 active sessions")
            return False
            
    except Exception as e:
        print(f"❌ TEST 2 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_3_get_session():
    """Test 3: Retrieve Session"""
    print_section("TEST 3: Get Session")
    
    try:
        service = get_session_service()
        
        # Get session by session_id
        session = service.get_session("1")
        
        if session:
            print(f"✅ Retrieved session by session_id")
            print(f"   Session ID: {session.session_id}")
            print(f"   User ID: {session.user_id}")
            print(f"   Status: {session.status}")
        else:
            print("❌ Failed to retrieve session by session_id")
            return False
        
        # Get session by user_id
        user_session = service.get_user_session("2")
        
        if user_session:
            print(f"\n✅ Retrieved session by user_id")
            print(f"   Session ID: {user_session.session_id}")
            print(f"   User ID: {user_session.user_id}")
        else:
            print("❌ Failed to retrieve session by user_id")
            return False
        
        # Try to get non-existent session
        missing_session = service.get_session("999")
        
        if missing_session is None:
            print(f"\n✅ Correctly returned None for non-existent session")
        else:
            print("❌ Should return None for non-existent session")
            return False
        
        print("\n✅ TEST 3 PASSED: Session retrieval works correctly")
        return True
            
    except Exception as e:
        print(f"❌ TEST 3 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_4_increment_requests():
    """Test 4: Increment Request Counter"""
    print_section("TEST 4: Increment Request Counter")
    
    try:
        service = get_session_service()
        
        session = service.get_session("1")
        initial_count = session.total_requests
        
        print(f"Initial request count: {initial_count}")
        
        # Increment 5 times
        for i in range(5):
            service.increment_request_count("1")
        
        session = service.get_session("1")
        new_count = session.total_requests
        
        print(f"After 5 increments: {new_count}")
        
        if new_count == initial_count + 5:
            print(f"✅ Request counter incremented correctly: {initial_count} → {new_count}")
            print("\n✅ TEST 4 PASSED: Request counting works")
            return True
        else:
            print(f"❌ Expected {initial_count + 5}, got {new_count}")
            return False
            
    except Exception as e:
        print(f"❌ TEST 4 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_5_end_session():
    """Test 5: End Session (Logout)"""
    print_section("TEST 5: End Session")
    
    try:
        service = get_session_service()
        
        # Get session before ending
        session = service.get_session("2")
        print(f"Session 2 status before logout: {session.status}")
        print(f"Session 2 logout_time before: {session.logout_time}")
        print(f"Session 2 total_requests: {session.total_requests}")
        
        # Wait a bit to have measurable duration
        time.sleep(1)
        
        # End the session
        result = service.end_session("2")
        
        if result:
            print(f"\n✅ Session ended successfully")
        else:
            print("❌ Failed to end session")
            return False
        
        # Try to get the session again (should be None)
        ended_session = service.get_session("2")
        
        if ended_session is None:
            print("✅ Session removed from active sessions")
        else:
            print("❌ Session still active after ending")
            return False
        
        # Check stats
        stats = service.get_stats()
        print(f"\n📊 Statistics after ending session:")
        print(f"   Active sessions: {stats['active_sessions']}")
        print(f"   Users online: {stats['users_online']}")
        
        # Check CSV file for completed session
        sessions_file = Path("logs/sessions.csv")
        with open(sessions_file, 'r') as f:
            lines = f.readlines()
            print(f"\n📄 sessions.csv has {len(lines)} lines")
            # Find the completed session
            for line in lines:
                if '"2"' in line or ',2,' in line:
                    print(f"   Session 2: {line.strip()}")
                    if "completed" in line:
                        print("   ✅ Session marked as 'completed'")
                    if "logout_time" in line or len(line.split(',')[3]) > 0:
                        print("   ✅ Logout time recorded")
        
        if stats['active_sessions'] == 1:
            print("\n✅ TEST 5 PASSED: Session ended correctly")
            return True
        else:
            print(f"\n❌ TEST 5 FAILED: Expected 1 active session, got {stats['active_sessions']}")
            return False
            
    except Exception as e:
        print(f"❌ TEST 5 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_6_multiple_login_same_user():
    """Test 6: Multiple Logins for Same User"""
    print_section("TEST 6: Multiple Logins Same User")
    
    try:
        service = get_session_service()
        
        # User 3 logs in first time
        session1 = service.create_session(
            user_id="3",
            username="multi_login",
            email="multi@company.com"
        )
        
        print(f"First login - Session ID: {session1.session_id}")
        
        stats1 = service.get_stats()
        print(f"Active sessions after first login: {stats1['active_sessions']}")
        
        # Same user logs in again (should close previous session)
        session2 = service.create_session(
            user_id="3",
            username="multi_login",
            email="multi@company.com"
        )
        
        print(f"\nSecond login - Session ID: {session2.session_id}")
        
        stats2 = service.get_stats()
        print(f"Active sessions after second login: {stats2['active_sessions']}")
        
        # Check if old session was closed
        old_session = service.get_session(session1.session_id)
        
        if old_session is None:
            print(f"\n✅ Old session {session1.session_id} was closed")
        else:
            print(f"\n❌ Old session {session1.session_id} still active")
            return False
        
        # Check if new session is active
        new_session = service.get_session(session2.session_id)
        
        if new_session:
            print(f"✅ New session {session2.session_id} is active")
        else:
            print(f"❌ New session {session2.session_id} not found")
            return False
        
        # Stats should still show 2 active sessions (user 1 and user 3)
        if stats2['active_sessions'] == 2:
            print("\n✅ TEST 6 PASSED: Multiple login handling works correctly")
            return True
        else:
            print(f"\n❌ TEST 6 FAILED: Expected 2 active sessions, got {stats2['active_sessions']}")
            return False
            
    except Exception as e:
        print(f"❌ TEST 6 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_7_shutdown():
    """Test 7: Graceful Shutdown"""
    print_section("TEST 7: Graceful Shutdown")
    
    try:
        service = get_session_service()
        
        stats_before = service.get_stats()
        print(f"Active sessions before shutdown: {stats_before['active_sessions']}")
        
        # Shutdown service
        service.shutdown()
        
        stats_after = service.get_stats()
        print(f"Active sessions after shutdown: {stats_after['active_sessions']}")
        
        # Check CSV file
        sessions_file = Path("logs/sessions.csv")
        with open(sessions_file, 'r') as f:
            lines = f.readlines()
            print(f"\n📄 sessions.csv has {len(lines)} lines")
            completed_count = sum(1 for line in lines if 'completed' in line)
            print(f"   Completed sessions: {completed_count}")
        
        if stats_after['active_sessions'] == 0:
            print("\n✅ TEST 7 PASSED: All sessions closed on shutdown")
            return True
        else:
            print(f"\n❌ TEST 7 FAILED: {stats_after['active_sessions']} sessions still active")
            return False
            
    except Exception as e:
        print(f"❌ TEST 7 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("\n" + "="*70)
    print("  SESSION SERVICE TEST SUITE")
    print("="*70)
    print(f"  Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    
    results = []
    
    # Run all tests
    results.append(("Initialization", test_1_initialization()))
    results.append(("Create Session", test_2_create_session()))
    results.append(("Get Session", test_3_get_session()))
    results.append(("Increment Requests", test_4_increment_requests()))
    results.append(("End Session", test_5_end_session()))
    results.append(("Multiple Login Same User", test_6_multiple_login_same_user()))
    results.append(("Graceful Shutdown", test_7_shutdown()))
    
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