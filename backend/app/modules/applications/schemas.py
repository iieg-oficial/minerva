from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ApplicationBase(BaseModel):
    name: str
    slug: str
    description: str | None = None
    homepage_url: str | None = None
    display_name: str | None = None
    logo_url: str | None = None
    brand_color: str | None = None


class ApplicationCreate(ApplicationBase):
    is_public: bool = False
    """Cliente público (SPA/móvil sin `client_secret`): el canje OIDC exige PKCE
    en su lugar. Si es `False` (default), se genera un `client_secret` como hoy."""


class ApplicationUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    homepage_url: str | None = None
    status: str | None = None
    display_name: str | None = None
    logo_url: str | None = None
    brand_color: str | None = None


class ApplicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    description: str | None = None
    client_id: str
    status: str
    homepage_url: str | None = None
    display_name: str | None = None
    logo_url: str | None = None
    brand_color: str | None = None
    created_at: datetime
    updated_at: datetime


class ApplicationBranding(BaseModel):
    """Datos públicos no sensibles para personalizar la pantalla de login.
    Nunca incluye client_secret, redirect_uris ni estado interno."""

    name: str
    display_name: str | None = None
    logo_url: str | None = None
    brand_color: str | None = None


class ApplicationWithSecrets(ApplicationRead):
    client_secret_hash: str | None = None


class RedirectURICreate(BaseModel):
    uri: str
    environment: str = "production"


class RedirectURIRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    application_id: str
    uri: str
    environment: str
