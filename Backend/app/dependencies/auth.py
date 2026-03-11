"""
Authentication Dependencies - DB-backed with role checks and user caching.
"""
import asyncio
import time
from typing import Dict, Optional, Tuple
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.utils.auth import verify_token
from app.database.users import get_user
from app.models.user import User

security = HTTPBearer()

# User cache: email -> (User, timestamp)
_user_cache: Dict[str, Tuple[object, float]] = {}
_user_cache_lock = asyncio.Lock()
_USER_CACHE_TTL = 30.0  # seconds


async def _get_user_cached(email: str):
    """Get user from cache or DB, with 30s TTL."""
    now = time.time()

    async with _user_cache_lock:
        if email in _user_cache:
            cached_user, cached_at = _user_cache[email]
            if now - cached_at < _USER_CACHE_TTL:
                return cached_user

    # Cache miss or expired — fetch from DB (outside lock)
    user = await get_user(email)

    if user is not None:
        async with _user_cache_lock:
            _user_cache[email] = (user, now)

    return user


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User:
    """Dependency to get current authenticated user from JWT token."""
    token = credentials.credentials

    username = verify_token(token)
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await _get_user_cached(username)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if user.disabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user",
        )

    current_user = User(**user.dict())
    request.state.user = current_user
    return current_user


async def get_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Dependency that requires the current user to be an admin."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Get current active user (convenience function)."""
    return current_user
