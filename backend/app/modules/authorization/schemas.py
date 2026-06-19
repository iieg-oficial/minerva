from pydantic import BaseModel, ConfigDict


class PermissionCheckRequest(BaseModel):
    user_id: str
    application_slug: str
    permission: str


class PermissionCheckResponse(BaseModel):
    allowed: bool
    reason: str


class UserMePermissionsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    application_slug: str
    roles: list[str]
    permissions: list[str]
