"""
Session Management Service
Tracks active user sessions, handles lifecycle, and manages session state.

Save as: app/services/session_service.py
"""
import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
import logging
from threading import RLock  # Changed from Lock to RLock

from app.utils.csv_logger import get_csv_logger

logger = logging.getLogger(__name__)


class Session:
    """Represents a user session"""
    
    def __init__(self, session_id: str, user_id: str):
        self.session_id = session_id
        self.user_id = user_id
        self.login_time = datetime.utcnow()
        self.last_activity = datetime.utcnow()
        self.logout_time: Optional[datetime] = None
        self.total_requests = 0
        self.status = "active"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary for CSV logging"""
        duration_mins = None
        if self.logout_time:
            duration = (self.logout_time - self.login_time).total_seconds() / 60
            duration_mins = round(duration, 2)
        
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "login_time": self.login_time.isoformat() + "Z",
            "logout_time": self.logout_time.isoformat() + "Z" if self.logout_time else None,
            "session_duration_mins": duration_mins,
            "total_requests": self.total_requests,
            "status": self.status
        }
    
    def increment_requests(self):
        """Increment request counter and update last activity time"""
        self.total_requests += 1
        self.last_activity = datetime.utcnow()
    
    def close(self):
        """Close the session"""
        self.logout_time = datetime.utcnow()
        self.status = "completed"


class SessionService:
    """Manages user sessions and session lifecycle"""
    
    def __init__(self, session_timeout_minutes: int = 30):
        """
        Initialize session service
        
        Args:
            session_timeout_minutes: Time in minutes before inactive session expires
        """
        self.active_sessions: Dict[str, Session] = {}  # session_id -> Session
        self.user_sessions: Dict[str, str] = {}  # user_id -> session_id
        self.session_timeout = timedelta(minutes=session_timeout_minutes)
        self._lock = RLock()  # Changed from Lock to RLock for reentrant locking
        self.csv_logger = get_csv_logger()
        self._session_counter = 0  # Counter for sequential session IDs
        
        logger.info(f"SessionService initialized (timeout: {session_timeout_minutes}m)")
    
    def generate_session_id(self) -> str:
        """Generate unique numeric session ID"""
        with self._lock:
            self._session_counter += 1
            return str(self._session_counter)
    
    def create_session(self, user_id: str, username: str, email: str) -> Session:
        """
        Create new session for user
        
        Args:
            user_id: User ID
            username: Username
            email: User email
            
        Returns:
            Session object
        """
        with self._lock:
            # Close existing session if any
            if user_id in self.user_sessions:
                old_session_id = self.user_sessions[user_id]
                self._end_session_internal(old_session_id)
            
            # Create new session
            session_id = self.generate_session_id()
            session = Session(session_id, user_id)
            
            # Store in memory
            self.active_sessions[session_id] = session
            self.user_sessions[user_id] = session_id
            
            # Log user data
            self.csv_logger.append_user({
                "user_id": user_id,
                "username": username,
                "email": email,
                "created_at": datetime.utcnow().isoformat() + "Z",
                "last_login": session.login_time.isoformat() + "Z"
            })
            
            # Log session start
            self.csv_logger.append_session(session.to_dict())
            
            logger.info(f"Created session {session_id} for user {user_id}")
            return session
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """
        Get session by session ID
        
        Args:
            session_id: Session ID
            
        Returns:
            Session object or None if not found
        """
        with self._lock:
            session = self.active_sessions.get(session_id)
            
            # Check if session expired
            if session and self._is_session_expired(session):
                logger.info(f"Session {session_id} expired due to timeout")
                self._end_session_internal(session_id)
                return None
            
            return session
    
    def get_user_session(self, user_id: str) -> Optional[Session]:
        """
        Get active session for user
        
        Args:
            user_id: User ID
            
        Returns:
            Session object or None if not found
        """
        with self._lock:
            session_id = self.user_sessions.get(user_id)
            if not session_id:
                return None
            
            return self.get_session(session_id)
    
    def _is_session_expired(self, session: Session) -> bool:
        """Check if session has expired due to inactivity"""
        if session.status != "active":
            return False

        elapsed = datetime.utcnow() - session.last_activity
        return elapsed > self.session_timeout
    
    def increment_request_count(self, session_id: str):
        """
        Increment request counter for session
        
        Args:
            session_id: Session ID
        """
        with self._lock:
            session = self.active_sessions.get(session_id)
            if session:
                session.increment_requests()
    
    def end_session(self, session_id: str) -> bool:
        """
        End a session (user logout)
        
        Args:
            session_id: Session ID
            
        Returns:
            bool: True if session was ended, False if not found
        """
        with self._lock:
            return self._end_session_internal(session_id)
    
    def _end_session_internal(self, session_id: str) -> bool:
        """Internal method to end session (must be called within lock)"""
        session = self.active_sessions.get(session_id)
        if not session:
            return False
        
        # Close session
        session.close()
        
        # Log session end to CSV
        self.csv_logger.append_session(session.to_dict())
        
        # Remove from active sessions
        del self.active_sessions[session_id]
        if session.user_id in self.user_sessions:
            del self.user_sessions[session.user_id]
        
        logger.info(f"Ended session {session_id} for user {session.user_id} "
                   f"(duration: {session.to_dict()['session_duration_mins']}m, "
                   f"requests: {session.total_requests})")
        
        return True
    
    def end_user_session(self, user_id: str) -> bool:
        """
        End session by user ID
        
        Args:
            user_id: User ID
            
        Returns:
            bool: True if session was ended, False if not found
        """
        with self._lock:
            session_id = self.user_sessions.get(user_id)
            if not session_id:
                return False
            return self._end_session_internal(session_id)
    
    def cleanup_expired_sessions(self):
        """Clean up all expired sessions"""
        with self._lock:
            expired_sessions = []
            
            for session_id, session in self.active_sessions.items():
                if self._is_session_expired(session):
                    expired_sessions.append(session_id)
            
            for session_id in expired_sessions:
                self._end_session_internal(session_id)
            
            if expired_sessions:
                logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")
    
    def get_active_sessions_count(self) -> int:
        """Get count of active sessions"""
        with self._lock:
            return len(self.active_sessions)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get session statistics"""
        with self._lock:
            return {
                "active_sessions": len(self.active_sessions),
                "users_online": len(self.user_sessions),
                "session_timeout_minutes": self.session_timeout.total_seconds() / 60
            }
    
    def shutdown(self):
        """Shutdown service and close all active sessions"""
        with self._lock:
            logger.info(f"Shutting down SessionService, closing {len(self.active_sessions)} active sessions")
            
            # Close all active sessions
            for session_id in list(self.active_sessions.keys()):
                self._end_session_internal(session_id)
            
            logger.info("SessionService shutdown complete")


# Global singleton instance
_session_service_instance: Optional[SessionService] = None


def get_session_service() -> SessionService:
    """Get or create the global session service instance"""
    global _session_service_instance
    if _session_service_instance is None:
        _session_service_instance = SessionService()
    return _session_service_instance


def init_session_service(session_timeout_minutes: int = 30) -> SessionService:
    """
    Initialize the session service with custom settings
    
    Args:
        session_timeout_minutes: Session timeout in minutes
        
    Returns:
        SessionService instance
    """
    global _session_service_instance
    _session_service_instance = SessionService(session_timeout_minutes)
    return _session_service_instance