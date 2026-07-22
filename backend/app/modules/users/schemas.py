from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserBase(BaseModel):
    email: str
    full_name: str


class UserCreate(UserBase):
    password: str = Field(min_length=8)
    domain: str | None = None


class UserUpdate(BaseModel):
    full_name: str | None = None
    email: str | None = None
    password: str | None = Field(default=None, min_length=8)
    status: str | None = None
    domain: str | None = None


class UserStatusUpdate(BaseModel):
    status: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    full_name: str
    status: str
    domain: str | None = None
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None
