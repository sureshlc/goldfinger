"""
User Database - Async DB-backed user operations.
Provides module-level functions used by auth dependencies and routers.
"""
from typing import Optional, Dict
from app.models.user import UserInDB
from app.database.connection import get_session_factory
import logging

logger = logging.getLogger(__name__)


def _row_to_user(db_user) -> UserInDB:
    """Convert a UserDB ORM object to a UserInDB Pydantic model."""
    return UserInDB(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        full_name=db_user.username,
        disabled=db_user.disabled,
        hashed_password=db_user.hashed_password,
        role=db_user.role,
    )


async def get_user(email: str) -> Optional[UserInDB]:
    """Get user from database by email."""
    from app.database.repositories.user_repo import get_user_by_email

    factory = get_session_factory()
    async with factory() as session:
        db_user = await get_user_by_email(session, email)
        if db_user:
            return _row_to_user(db_user)
        return None


async def authenticate_user(email: str, password: str) -> Optional[UserInDB]:
    """Authenticate a user with email and password."""
    from app.database.repositories.user_repo import authenticate_user as auth_user

    factory = get_session_factory()
    async with factory() as session:
        db_user = await auth_user(session, email, password)
        if db_user:
            return _row_to_user(db_user)
        return None


async def get_user_by_id(user_id: int) -> Optional[UserInDB]:
    """Get user by numeric ID."""
    from app.database.repositories.user_repo import get_user_by_id as get_by_id

    factory = get_session_factory()
    async with factory() as session:
        db_user = await get_by_id(session, user_id)
        if db_user:
            return _row_to_user(db_user)
        return None
