from datetime import datetime

from pydantic import BaseModel, Field

from app.shared.validators import NewPassword


class CredentialDestination(BaseModel):
    """Aplicación a la que se manda a la persona después de fijar su contraseña."""

    id: str
    name: str
    homepage_url: str


class CredentialLinkIn(BaseModel):
    application_id: str | None = None


class CredentialLink(BaseModel):
    """Enlace para entregar a la persona. Solo se muestra una vez: no se puede recuperar."""

    url: str
    purpose: str
    expires_at: datetime
    application: CredentialDestination | None = None


class CredentialTokenIn(BaseModel):
    token: str = Field(min_length=1, max_length=128)


class CredentialInspection(BaseModel):
    """Qué es el enlace y de quién, para mostrarlo antes de pedir la contraseña."""

    purpose: str
    email: str  # enmascarado
    expires_at: datetime
    application: CredentialDestination | None = None


class CredentialSet(CredentialTokenIn):
    password: NewPassword
