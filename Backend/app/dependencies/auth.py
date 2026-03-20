"""
Authentication Dependencies - DB-backed with role checks and user caching.
Supports dual auth: JWT Bearer tokens and X-API-Key header.
"""
import asyncio
import hashlib
import time
from typing import Dict, Optional, Tuple
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.utils.auth import verify_token
from app.database.users import get_user
from app.database.connection import get_session_factory
from app.models.user import User

security = HTTPBearer(auto_error=False)

SERVICE_USER = User(id=0, username="api-service", email="service@api.goldfinger.internal.io", role="service", disabled=False)

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


async def _authenticate_api_key(api_key: str) -> Optional[User]:
    """Authenticate via X-API-Key header. Returns SERVICE_USER if valid."""
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    factory = get_session_factory()
    async with factory() as session:
        from app.database.repositories.api_key_repo import get_api_key_by_hash, update_last_used

        db_key = await get_api_key_by_hash(session, key_hash)
        if db_key is None or not db_key.is_active:
            return None

        await update_last_used(session, db_key.id)
        await session.commit()

    return SERVICE_USER


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> User:
    """Dependency to get current authenticated user from JWT token or API key."""

    # Path A: JWT Bearer token
    if credentials is not None:
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

    # Path B: X-API-Key header
    api_key = request.headers.get("X-API-Key")
    if api_key:
        user = await _authenticate_api_key(api_key)
        if user is not None:
            request.state.user = user
            return user
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked API key",
        )

    # Path C: No credentials
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


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
