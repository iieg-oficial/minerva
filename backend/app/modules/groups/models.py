import uuid
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


class Group(SQLModel, table=True):
    __tablename__ = "groups"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    name: str = Field(max_length=255)
    slug: str = Field(unique=True, index=True, max_length=255)
    description: str | None = Field(default=None)
    source: str | None = Field(default=None, max_length=50)
    external_group_id: str | None = Field(default=None, max_length=255)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GroupUser(SQLModel, table=True):
    __tablename__ = "group_users"

    group_id: str = Field(foreign_key="groups.id", primary_key=True)
    user_id: str = Field(foreign_key="users.id", primary_key=True)


class GroupRole(SQLModel, table=True):
    __tablename__ = "group_roles"

    group_id: str = Field(foreign_key="groups.id", primary_key=True)
    role_id: str = Field(foreign_key="roles.id", primary_key=True)


class UserRole(SQLModel, table=True):
    __tablename__ = "user_roles"

    user_id: str = Field(foreign_key="users.id", primary_key=True)
    role_id: str = Field(foreign_key="roles.id", primary_key=True)
