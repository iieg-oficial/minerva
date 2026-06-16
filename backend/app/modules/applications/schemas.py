from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ApplicationBase(BaseModel):
    name: str
    slug: str
    description: str | None = None
    homepage_url: str | None = None


class ApplicationCreate(ApplicationBase):
    pass


class ApplicationUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    homepage_url: str | None = None
    status: str | None = None


class ApplicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    description: str | None = None
    client_id: str
    status: str
    homepage_url: str | None = None
    created_at: datetime
    updated_at: datetime


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
