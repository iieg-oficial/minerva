from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

from app.modules.credentials.schemas import CredentialLink


class UserBase(BaseModel):
    email: str
    full_name: str = Field(min_length=6, max_length=255)


class UserCreate(UserBase):
    # El admin no fija contraseña: el usuario queda `pending` y se emite un enlace de invitación.
    domain: str | None = None


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=6, max_length=255)
    email: str | None = None
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
    password_change_required: bool = False
    domain: str | None = None
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None


class UserCreated(UserRead):
    """Alta de usuario. Si se creó sin contraseña, trae el enlace de invitación para
    entregarlo a la persona: se muestra una sola vez."""

    credential_link: CredentialLink | None = None
