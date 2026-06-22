import uuid
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


class RefreshToken(SQLModel, table=True):
    """Refresh token con rotación y detección de reúso.

    Se guarda solo el HASH del token (nunca el valor en claro). Cada uso rota el
    token: el actual pasa a `rotated` y se emite uno nuevo en la misma `family_id`.
    Si se presenta un token ya `rotated`/`revoked` (reúso → posible robo), se
    revoca toda la familia. `access_jti` permite revocar el access token asociado.
    """

    __tablename__ = "refresh_tokens"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    token_hash: str = Field(unique=True, index=True)
    family_id: str = Field(index=True)
    user_id: str = Field(foreign_key="users.id")
    client_id: str = Field(foreign_key="applications.client_id")
    scope: str | None = Field(default=None)
    access_jti: str | None = Field(default=None)  # jti del access token emitido junto a este refresh
    status: str = Field(default="active")  # active | rotated | revoked
    expires_at: datetime = Field()
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AuthCode(SQLModel, table=True):
    __tablename__ = "auth_codes"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    code: str = Field(unique=True, index=True)
    client_id: str = Field(foreign_key="applications.client_id")
    user_id: str = Field(foreign_key="users.id")
    redirect_uri: str = Field(max_length=2048)
    scope: str | None = Field(default=None)
    # PKCE (RFC 7636): el cliente envía el challenge en /authorize y prueba la
    # posesión del verifier en /token. Protege el código contra interceptación.
    code_challenge: str | None = Field(default=None)
    code_challenge_method: str | None = Field(default=None)  # solo S256
    # OIDC: el nonce vincula el id_token a la sesión del cliente (anti-replay);
    # auth_time es el instante en que el usuario se autenticó.
    nonce: str | None = Field(default=None)
    auth_time: int | None = Field(default=None)
    expires_at: datetime = Field()
    used: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
