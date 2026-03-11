"""
User Repository - Database operations for users.
"""
from typing import Optional, List
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import UserDB
from app.utils.auth import get_password_hash, verify_password, verify_password_async


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[UserDB]:
    result = await db.execute(select(UserDB).where(UserDB.email == email))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[UserDB]:
    result = await db.execute(select(UserDB).where(UserDB.id == user_id))
    return result.scalar_one_or_none()


async def authenticate_user(db: AsyncSession, email: str, password: str) -> Optional[UserDB]:
    user = await get_user_by_email(db, email)
    if not user:
        return None
    if not await verify_password_async(password, user.hashed_password):
        return None
    return user


async def get_all_users(db: AsyncSession) -> List[UserDB]:
    result = await db.execute(select(UserDB).order_by(UserDB.id))
    return list(result.scalars().all())


async def create_user(
    db: AsyncSession,
    email: str,
    username: str,
    password: str,
    role: str = "user",
) -> UserDB:
    user = UserDB(
        email=email,
        username=username,
        hashed_password=get_password_hash(password),
        role=role,
        disabled=False,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


async def update_user(db: AsyncSession, user_id: int, **fields) -> Optional[UserDB]:
    user = await get_user_by_id(db, user_id)
    if not user:
        return None
    for key, value in fields.items():
        if key == "password":
            setattr(user, "hashed_password", get_password_hash(value))
        elif hasattr(user, key):
            setattr(user, key, value)
    await db.flush()
    await db.refresh(user)
    return user


async def delete_user(db: AsyncSession, user_id: int) -> bool:
    user = await get_user_by_id(db, user_id)
    if not user:
        return False
    await db.delete(user)
    await db.flush()
    return True


async def update_last_login(db: AsyncSession, user_id: int):
    from datetime import datetime, timezone
    await db.execute(
        update(UserDB)
        .where(UserDB.id == user_id)
        .values(last_login=datetime.now(timezone.utc))
    )
    await db.flush()
