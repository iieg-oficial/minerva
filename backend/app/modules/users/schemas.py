from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.shared.validators import validate_password_max_bytes


class UserBase(BaseModel):
    email: str
    full_name: str = Field(max_length=255)


class UserCreate(UserBase):
    password: Annotated[str, Field(min_length=8), AfterValidator(validate_password_max_bytes)]
    domain: str | None = None


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=255)
    email: str | None = None
    password: Annotated[str | None, Field(min_length=8), AfterValidator(validate_password_max_bytes)] = None
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
