from pydantic import BaseModel, Field

from app.modules.credentials.schemas import CredentialLink


class DelegatedRoleRead(BaseModel):
    """Rol de la aplicación. `delegable=False` marca los roles que dan administración
    delegada: esos solo los asigna un administrador de Minerva."""

    id: str
    slug: str
    name: str
    description: str | None = None
    delegable: bool = True


class DelegatedUserRole(BaseModel):
    id: str
    slug: str
    name: str
    # `group`: lo hereda de un grupo y no se puede quitar por delegación.
    via: str


class DelegatedUserRead(BaseModel):
    id: str
    email: str
    full_name: str
    status: str
    roles: list[DelegatedUserRole] = []


class DelegatedUserCreate(BaseModel):
    email: str
    full_name: str = Field(min_length=6, max_length=255)
    role_ids: list[str] = []


class DelegatedUserCreated(DelegatedUserRead):
    """`created=False` cuando el correo ya existía: no se toca la cuenta ni se emite enlace."""

    created: bool
    credential_link: CredentialLink | None = None


class DelegatedRolesUpdate(BaseModel):
    role_ids: list[str]
