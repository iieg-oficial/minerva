from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    actor_user_id: str | None = None
    action: str
    target_type: str | None = None
    target_id: str | None = None
    application_id: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    event_metadata: dict | None = None
    created_at: datetime


class AuditQuery(BaseModel):
    actor_user_id: str | None = None
    action: str | None = None
    target_type: str | None = None
    application_id: str | None = None
    limit: int = 100
    offset: int = 0
