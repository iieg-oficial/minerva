import uuid
from datetime import datetime, timezone

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class Application(SQLModel, table=True):
    __tablename__ = "applications"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    name: str = Field(max_length=255)
    slug: str = Field(unique=True, index=True, max_length=100)
    description: str | None = Field(default=None, max_length=1024)
    client_id: str = Field(default_factory=lambda: str(uuid.uuid4()), unique=True, index=True)
    client_secret_hash: str | None = Field(default=None)
    status: str = Field(default="active", max_length=20)
    homepage_url: str | None = Field(default=None, max_length=2048)
    # Branding opcional para la pantalla de login (issue #12). Datos no sensibles
    # que se exponen en un endpoint público para personalizar el "Iniciar sesión en …".
    display_name: str | None = Field(default=None, max_length=255)
    logo_url: str | None = Field(default=None, max_length=2048)
    brand_color: str | None = Field(default=None, max_length=32)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RedirectURI(SQLModel, table=True):
    __tablename__ = "redirect_uris"

    # Una URI por aplicación: mismo invariante que `Role`/`Permission` (issue #76).
    __table_args__ = (UniqueConstraint("application_id", "uri", name="uq_redirect_uris_application_id_uri"),)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    application_id: str = Field(foreign_key="applications.id", index=True)
    uri: str = Field(max_length=2048)
    environment: str = Field(default="production", max_length=20)
