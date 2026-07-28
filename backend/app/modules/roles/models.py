import uuid
from datetime import datetime, timezone

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class Role(SQLModel, table=True):
    __tablename__ = "roles"

    # Un rol por (aplicación, slug): sin esto, dos altas concurrentes (API o
    # importación de manifiesto) podían dejar dos filas para la misma clave de
    # dominio (issue #76). La migración 011 concilia duplicados preexistentes.
    __table_args__ = (UniqueConstraint("application_id", "slug", name="uq_roles_application_id_slug"),)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    application_id: str = Field(foreign_key="applications.id", index=True)
    name: str = Field(max_length=255)
    slug: str = Field(max_length=255)
    description: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
