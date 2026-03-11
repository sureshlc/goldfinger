"""
Authentication Router - With Session Tracking, Rate Limiting, and Token Blacklist.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from datetime import datetime, timedelta
from collections import defaultdict
from threading import Lock
from pydantic import BaseModel
from typing import Optional
from app.models.user import Token, User
from app.database.users import authenticate_user
from app.utils.auth import create_access_token, blacklist_token
from app.dependencies.auth import get_current_user, security
from app.services.session_service import get_session_service
from app.config import settings
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

# Rate limiting state
_login_attempts: dict = defaultdict(list)
_rate_limit_lock = Lock()
_MAX_LOGIN_ATTEMPTS = 5
_RATE_LIMIT_WINDOW = timedelta(minutes=5)


def _check_rate_limit(client_ip: str) -> bool:
    now = datetime.utcnow()
    with _rate_limit_lock:
        attempts = _login_attempts[client_ip]
        cutoff = now - _RATE_LIMIT_WINDOW
        _login_attempts[client_ip] = [t for t in attempts if t > cutoff]
        return len(_login_attempts[client_ip]) < _MAX_LOGIN_ATTEMPTS


def _record_login_attempt(client_ip: str):
    with _rate_limit_lock:
        _login_attempts[client_ip].append(datetime.utcnow())


@router.post("/login", response_model=Token)
async def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    """Login endpoint - returns JWT token."""
    client_ip = request.client.host if request.client else "unknown"

    if not _check_rate_limit(client_ip):
        logger.warning(f"Rate limit exceeded for IP: {client_ip}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again later.",
        )

    _record_login_attempt(client_ip)

    user = await authenticate_user(form_data.username, form_data.password)

    if not user:
        logger.warning(f"Failed login attempt for email: {form_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Update last login
    try:
        from app.database.connection import get_session_factory
        from app.database.repositories.user_repo import update_last_login

        factory = get_session_factory()
        async with factory() as session:
            await update_last_login(session, user.id)
            await session.commit()
    except Exception as e:
        logger.warning(f"Failed to update last_login: {e}")

    # Create session
    session_service = get_session_service()
    session = session_service.create_session(
        user_id=str(user.id),
        username=user.username,
        email=user.email,
    )
    logger.info(f"Session {session.session_id} created for user {user.email} (ID: {user.id})")

    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={
            "sub": user.email,
            "user_id": user.id,
            "session_id": session.session_id,
            "role": user.role,
        },
        expires_delta=access_token_expires,
    )

    logger.info(f"User {user.email} logged in successfully")

    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/logout")
async def logout(
    current_user: User = Depends(get_current_user),
    credentials=Depends(security),
):
    """Logout endpoint - ends user session and blacklists token."""
    session_service = get_session_service()
    user_id_str = str(current_user.id)

    logger.info(f"Logout request for user {current_user.email} (ID: {user_id_str})")

    raw_token = credentials.credentials
    from jose import jwt as jose_jwt

    try:
        payload = jose_jwt.decode(
            raw_token, settings.secret_key, algorithms=[settings.algorithm]
        )
        exp = payload.get("exp")
        if exp:
            expires_at = datetime.utcfromtimestamp(exp)
            blacklist_token(raw_token, expires_at)
    except Exception:
        pass

    success = session_service.end_user_session(user_id_str)

    if success:
        logger.info(f"User {current_user.email} (ID: {user_id_str}) logged out successfully")
        return {"message": "Successfully logged out", "status": "success"}
    else:
        logger.warning(f"No active session found for user {user_id_str}")
        return {"message": "No active session found", "status": "warning"}


@router.get("/me")
async def read_users_me(current_user: User = Depends(get_current_user)):
    """Get current user info including role."""
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "disabled": current_user.disabled,
        "role": current_user.role,
    }


def _validate_password_strength(password: str) -> None:
    """Enforce minimum password requirements."""
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    if not any(c.isupper() for c in password):
        raise HTTPException(status_code=400, detail="Password must contain at least one uppercase letter")
    if not any(c.isdigit() for c in password):
        raise HTTPException(status_code=400, detail="Password must contain at least one digit")


class ProfileUpdate(BaseModel):
    username: Optional[str] = None
    current_password: Optional[str] = None
    new_password: Optional[str] = None


@router.put("/profile")
async def update_profile(
    body: ProfileUpdate,
    current_user: User = Depends(get_current_user),
):
    """Update own profile (name and/or password)."""
    from app.database.connection import get_session_factory
    from app.database.repositories.user_repo import update_user, get_user_by_id
    from app.utils.auth import verify_password

    factory = get_session_factory()
    async with factory() as session:
        db_user = await get_user_by_id(session, current_user.id)
        if not db_user:
            raise HTTPException(status_code=404, detail="User not found")

        updates = {}

        if body.username is not None:
            updates["username"] = body.username

        if body.new_password:
            if not body.current_password:
                raise HTTPException(
                    status_code=400,
                    detail="Current password required to change password",
                )
            if not verify_password(body.current_password, db_user.hashed_password):
                raise HTTPException(
                    status_code=400,
                    detail="Current password is incorrect",
                )
            _validate_password_strength(body.new_password)
            updates["password"] = body.new_password

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        updated = await update_user(session, current_user.id, **updates)
        await session.commit()

        return {
            "message": "Profile updated successfully",
            "username": updated.username,
            "email": updated.email,
        }
