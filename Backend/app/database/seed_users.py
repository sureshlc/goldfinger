"""
Seed Users Script - Populates users table with initial data.
Run: python -m app.database.seed_users
"""
import asyncio
import getpass
from app.database.connection import init_db, close_db, get_session_factory
from app.database.repositories.user_repo import create_user, get_user_by_email

USERS = [
    {"email": "smittal@eaglebeverage.com", "username": "Shivam Mittal", "role": "user"},
    {"email": "schakravarthy@eaglebeverage.com", "username": "Suresh Chakravarthy", "role": "user"},
    {"email": "admin@eaglebeverage.com", "username": "Admin", "role": "admin"},
    {"email": "tsurber@eaglebeverage.com", "username": "Tiffini Surber", "role": "user"},
    {"email": "cwilson@eaglebeverage.com", "username": "Charlton Wilson", "role": "user"},
    {"email": "cadams@eaglebeverage.com", "username": "Colby Adams", "role": "user"},
    {"email": "mcogert@eaglebeverage.com", "username": "Max Cogert", "role": "user"},
]


async def seed():
    await init_db()
    factory = get_session_factory()

    print("\n" + "=" * 60)
    print("  SEEDING USERS")
    print("=" * 60)

    async with factory() as session:
        for user_info in USERS:
            existing = await get_user_by_email(session, user_info["email"])
            if existing:
                print(f"  [SKIP] {user_info['email']} already exists (id={existing.id})")
                continue

            password = getpass.getpass(
                f"  Password for {user_info['username']} ({user_info['email']}): "
            )
            if not password.strip():
                print("  [SKIP] Empty password, skipping user")
                continue

            user = await create_user(
                session,
                email=user_info["email"],
                username=user_info["username"],
                password=password,
                role=user_info["role"],
            )
            print(f"  [OK] Created user {user.id}: {user.email} (role={user.role})")

        await session.commit()

    print("\n  Seeding complete!")
    print("=" * 60 + "\n")
    await close_db()


if __name__ == "__main__":
    asyncio.run(seed())
