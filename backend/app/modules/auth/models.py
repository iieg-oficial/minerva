import uuid
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


class AuthCode(SQLModel, table=True):
    __tablename__ = "auth_codes"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    code: str = Field(unique=True, index=True)
    client_id: str = Field(foreign_key="applications.client_id")
    user_id: str = Field(foreign_key="users.id")
    redirect_uri: str = Field(max_length=2048)
    scope: str | None = Field(default=None)
    expires_at: datetime = Field()
    used: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
