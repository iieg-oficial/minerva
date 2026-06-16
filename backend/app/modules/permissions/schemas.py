from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PermissionBase(BaseModel):
    name: str
    slug: str
    description: str | None = None


class PermissionCreate(PermissionBase):
    pass


class PermissionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class PermissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    application_id: str
    name: str
    slug: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime
