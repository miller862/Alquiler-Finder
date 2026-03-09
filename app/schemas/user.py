from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import Optional


class UserCreate(BaseModel):
    username: str
    password: str
    is_admin: bool = False

    @field_validator("username")
    @classmethod
    def username_lower(cls, v: str) -> str:
        return v.strip().lower()


class UserRead(BaseModel):
    id: int
    username: str
    is_admin: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class LoginForm(BaseModel):
    username: str
    password: str
