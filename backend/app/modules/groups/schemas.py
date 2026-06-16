from datetime import datetime

from pydantic import BaseModel, ConfigDict


class GroupBase(BaseModel):
    name: str
    slug: str
    description: str | None = None
    source: str | None = None
    external_group_id: str | None = None


class GroupCreate(GroupBase):
    pass


class GroupUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class GroupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    description: str | None = None
    source: str | None = None
    external_group_id: str | None = None
    created_at: datetime
    updated_at: datetime
