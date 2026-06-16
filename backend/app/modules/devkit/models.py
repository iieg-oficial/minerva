import uuid
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


class ManifestImport(SQLModel, table=True):
    __tablename__ = "manifest_imports"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    application_id: str | None = Field(default=None, foreign_key="applications.id", index=True)
    application_code: str = Field(index=True, max_length=100)
    source: str = Field(max_length=512)
    checksum: str | None = Field(default=None, max_length=64)
    status: str = Field(default="success", max_length=20)
    message: str | None = Field(default=None)
    permissions_count: int = Field(default=0)
    roles_count: int = Field(default=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
