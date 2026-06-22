import uuid
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


class SigningKey(SQLModel, table=True):
    """Par de claves de firma de tokens (RS256).

    La clave activa firma los tokens nuevos; las `retired` se siguen publicando en
    el JWKS hasta que expiren todos los tokens emitidos con ellas (ventana de
    solapamiento para rotación).

    Convención del proyecto: PK como `str`, timestamps UTC.
    `private_key_pem` se guarda CIFRADO en reposo (Fernet, ver app/core/crypto.py).
    """

    __tablename__ = "signing_keys"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    kid: str = Field(unique=True, index=True)  # key ID — va en el header del JWT
    algorithm: str = Field(default="RS256")
    private_key_pem: str  # cifrado en reposo (NUNCA en texto plano)
    public_key_pem: str
    status: str = Field(default="active")  # active | retired
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    rotated_at: datetime | None = Field(default=None)
