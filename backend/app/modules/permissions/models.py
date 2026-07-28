import uuid
from datetime import datetime, timezone

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class Permission(SQLModel, table=True):
    __tablename__ = "permissions"

    # Un permiso por (aplicación, slug): mismo invariante que `Role` (issue #76).
    __table_args__ = (UniqueConstraint("application_id", "slug", name="uq_permissions_application_id_slug"),)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    application_id: str = Field(foreign_key="applications.id", index=True)
    name: str = Field(max_length=255)
    slug: str = Field(max_length=255)
    description: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RolePermission(SQLModel, table=True):
    __tablename__ = "role_permissions"

    role_id: str = Field(foreign_key="roles.id", primary_key=True)
    permission_id: str = Field(foreign_key="permissions.id", primary_key=True)
