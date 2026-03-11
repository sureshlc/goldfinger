"""
Authentication Utilities with Full Token Payload Support
Save as: app/utils/auth.py
"""
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict
from threading import Lock
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.config import settings
from app.models.user import TokenData

# Password hashing context - using argon2 instead of bcrypt
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# Token blacklist: hash -> expires_at
_token_blacklist: Dict[str, datetime] = {}
_blacklist_lock = Lock()


def _hash_token(token: str) -> str:
    """Hash a token for storage in the blacklist."""
    return hashlib.sha256(token.encode()).hexdigest()


def blacklist_token(token: str, expires_at: datetime):
    """Add a token to the blacklist."""
    token_hash = _hash_token(token)
    with _blacklist_lock:
        _token_blacklist[token_hash] = expires_at
        # Auto-cleanup expired entries
        now = datetime.utcnow()
        expired = [h for h, exp in _token_blacklist.items() if exp < now]
        for h in expired:
            del _token_blacklist[h]


def is_token_blacklisted(token: str) -> bool:
    """Check if a token has been blacklisted."""
    token_hash = _hash_token(token)
    with _blacklist_lock:
        if token_hash in _token_blacklist:
            # Check if it's still valid (not yet expired)
            if _token_blacklist[token_hash] >= datetime.utcnow():
                return True
            else:
                # Expired, remove it
                del _token_blacklist[token_hash]
        return False

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Hash a password"""
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt

def verify_token(token: str) -> Optional[str]:
    """
    Verify a JWT token and return the username (for backward compatibility)
    """
    # Check blacklist before decoding
    if is_token_blacklisted(token):
        return None
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        username: str = payload.get("sub")
        if username is None:
            return None
        return username
    except JWTError:
        return None

def decode_token(token: str) -> Optional[TokenData]:
    """
    Decode a JWT token and return full token data including user_id and session_id
    """
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        username: str = payload.get("sub")
        user_id: int = payload.get("user_id")
        session_id: str = payload.get("session_id")
        
        if username is None:
            return None
        
        return TokenData(
            username=username,
            user_id=int(user_id) if user_id else None,
            session_id=session_id
        )
    except JWTError:
        return None
    except (ValueError, TypeError):
        return None