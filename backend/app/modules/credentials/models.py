import uuid
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


class CredentialToken(SQLModel, table=True):
    """Enlace de un solo uso para que una persona fije su contraseña.

    Se guarda solo el HASH del token; el valor en claro sale una vez, dentro del enlace.
    `purpose` distingue invitación (alta sin credencial), restablecimiento (lo emite un
    admin) y cambio obligatorio (lo emite el login). `used_at` marca el canje o el
    reemplazo por un enlace más nuevo: en ambos casos deja de servir.
    """

    __tablename__ = "credential_tokens"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    token_hash: str = Field(unique=True, index=True)
    purpose: str = Field(max_length=20)  # invite | reset | forced_change
    expires_at: datetime = Field()
    used_at: datetime | None = Field(default=None)
    created_by: str | None = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
