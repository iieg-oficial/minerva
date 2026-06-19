from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# --- Auth dev ---------------------------------------------------------------
class DevLoginRequest(BaseModel):
    email: EmailStr
    full_name: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


# --- Me ---------------------------------------------------------------------
class MeResponse(BaseModel):
    id: str
    email: str
    full_name: str
    status: str


class MePermissionsResponse(BaseModel):
    application: str
    roles: list[str]
    permissions: list[str]


# --- Access assignments -----------------------------------------------------
class AccessAssignmentCreate(BaseModel):
    user_id: str
    role_id: str


class AccessAssignmentRead(BaseModel):
    id: str
    user_id: str
    role_id: str
    role_name: str
    role_slug: str
    application_id: str
    application_code: str


# --- Manifests --------------------------------------------------------------
class ManifestImportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    application_id: str | None = None
    application_code: str
    source: str
    status: str
    message: str | None = None
    permissions_count: int
    roles_count: int
    created_at: datetime


class ManifestImportResult(BaseModel):
    application_id: str
    application_code: str
    created_application: bool
    permissions_upserted: int
    roles_upserted: int
    role_permissions_linked: int
    import_id: str


class ManifestImportRequest(BaseModel):
    """Importar un manifiesto enviando su contenido YAML como texto plano."""

    content: str = Field(..., description="Contenido del archivo manifest.minerva.yml")
    source: str | None = Field(default=None, description="Nombre/origen del manifiesto, p. ej. manifest.minerva.yml")
