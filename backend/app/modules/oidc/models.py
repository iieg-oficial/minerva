import uuid
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


class SigningKey(SQLModel, table=True):
    """Par de claves de firma de tokens (RS256).

    Ciclo de vida: `pending` -> `active` -> `retired` -> purga.

    - `pending`: ya se publica en el JWKS pero todavía NO firma nada. Existe para que
      los verificadores la tengan cacheada antes de ver el primer token firmado con
      ella (publish-before-use); se promueve pasada `MINERVA_KEY_PROPAGATION_MINUTES`.
    - `active`: la única que firma tokens nuevos.
    - `retired`: se sigue publicando hasta que expire el último token emitido con ella
      (`key_retirement_overlap_minutes`), y solo entonces se purga.

    Convención del proyecto: PK como `str`, timestamps UTC.
    `private_key_pem` se guarda CIFRADO en reposo (Fernet, ver app/core/crypto.py).
    """

    __tablename__ = "signing_keys"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    kid: str = Field(unique=True, index=True)  # key ID — va en el header del JWT
    algorithm: str = Field(default="RS256")
    private_key_pem: str  # cifrado en reposo (NUNCA en texto plano)
    public_key_pem: str
    status: str = Field(default="active")  # pending | active | retired
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    rotated_at: datetime | None = Field(default=None)
