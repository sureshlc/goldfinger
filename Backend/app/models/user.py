"""
User Models with role-based access.
"""
from pydantic import BaseModel, EmailStr
from typing import Optional


class User(BaseModel):
    id: int
    username: str
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    disabled: Optional[bool] = False
    role: str = "user"


class UserInDB(User):
    hashed_password: str


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None
    user_id: Optional[int] = None
    session_id: Optional[str] = None
