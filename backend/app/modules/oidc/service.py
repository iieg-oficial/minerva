import uuid
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwk
from sqlmodel import Session

from app.core.crypto import decrypt_secret, encrypt_secret
from app.core.exceptions import AppException, ConflictError
from app.core.security import create_access_token_rs256, create_dev_token_rs256
from app.modules.oidc.models import SigningKey
from app.modules.oidc.repository import SigningKeyRepository
from app.modules.users.models import User


def claims_for_scopes(user: User, scope: str) -> dict:
    """Mapea scopes OIDC a claims de identidad (OIDC Core 5.4). No incluye `sub`:
    es obligatorio y el caller siempre lo fija aparte, sin depender del scope."""
    scopes = set(scope.split())
    claims: dict = {}
    if "profile" in scopes:
        claims["name"] = user.full_name
        claims["preferred_username"] = user.email
    if "email" in scopes:
        claims["email"] = user.email
        claims["email_verified"] = user.auth_provider == "google"
    return claims


def _as_utc(value: datetime) -> datetime:
    """Normaliza a UTC un timestamp leído de la BD. SQLite (y PostgreSQL con columnas
    sin timezone) devuelve `datetime` naive; el proyecto siempre los guarda en UTC, así
    que asumir UTC al leerlos evita comparar naive contra aware."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _generate_rsa_keypair() -> tuple[str, str]:
    """Genera un par RSA 2048 y devuelve (private_pem, public_pem) en texto PEM."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return private_pem, public_pem


class OIDCService:
    """Gestión de claves de firma y construcción del JWKS."""

    def __init__(self, session: Session):
        self.session = session
        self.repo = SigningKeyRepository(session)

    def generate_signing_key(self, status: str = "active") -> SigningKey:
        """Genera un par RSA nuevo, cifra la clave privada y lo persiste.

        `status="pending"` lo publica en el JWKS sin que firme nada todavía
        (publish-before-use, ver `stage_key`)."""
        private_pem, public_pem = _generate_rsa_keypair()
        key = SigningKey(
            kid=uuid.uuid4().hex,
            algorithm="RS256",
            private_key_pem=encrypt_secret(private_pem),
            public_key_pem=public_pem,
            status=status,
        )
        return self.repo.create(key)

    def get_active_signing_key(self) -> SigningKey:
        key = self.repo.get_active()
        if key is None:
            raise AppException(status_code=500, detail="No hay clave de firma activa configurada")
        return key

    def get_active_private_pem(self) -> tuple[str, str]:
        """Devuelve (kid, private_pem descifrado) de la clave activa, para firmar."""
        key = self.get_active_signing_key()
        return key.kid, decrypt_secret(key.private_key_pem)

    def ensure_active_signing_key(self) -> SigningKey:
        """Idempotente: usado en el seeding del arranque. Genera la clave si no existe."""
        existing = self.repo.get_active()
        return existing or self.generate_signing_key()

    def build_jwks(self) -> dict:
        """Construye el JWKS (RFC 7517) con las claves publicables (activa + retiradas)."""
        keys = []
        for key in self.repo.list_publishable():
            jwk_dict = jwk.construct(key.public_key_pem, algorithm=key.algorithm).to_dict()
            jwk_dict.update({"kid": key.kid, "use": "sig", "alg": key.algorithm})
            # Los valores n/e que devuelve jose pueden venir como bytes; normaliza a str.
            jwk_dict = {k: (v.decode() if isinstance(v, bytes) else v) for k, v in jwk_dict.items()}
            keys.append(jwk_dict)
        return {"keys": keys}

    # --- Rotación en dos fases (publish-before-use) ------------------------
    # Firmar de inmediato con una clave recién creada corta el servicio: los
    # verificadores (el propio backend vía Redis, el SDK vía su caché de 1 h, y
    # cualquier consumidor OIDC estándar) todavía no la tienen. Por eso la clave se
    # publica primero como `pending` y solo se promueve pasada la ventana de
    # propagación, cuando ya está en las cachés de todos.

    def stage_key(self) -> SigningKey:
        """Fase 1: publica una clave nueva en el JWKS sin firmar con ella.

"""
        if self.repo.get_pending() is not None:
            raise ConflictError(
                detail="Ya hay una clave pendiente de promover; promuévela o descártala antes de publicar otra"
            )
        return self.generate_signing_key(status="pending")

    def promote_key(self, force: bool = False) -> SigningKey:
        """Fase 2: activa la clave pendiente, retira la anterior y purga las vencidas.

        Rechaza la promoción si no ha pasado la ventana de propagación, porque en ese
        momento todavía hay verificadores con un JWKS cacheado sin la clave nueva:
        promover ahí es exactamente el corte de servicio que este flujo evita. `force`
        la salta a propósito (clave comprometida)."""
        from app.core.config import settings

        pending = self.repo.get_pending()
        if pending is None:
            raise ConflictError(detail="No hay ninguna clave pendiente de promover; publica una primero")

        ready_at = _as_utc(pending.created_at) + timedelta(minutes=settings.MINERVA_KEY_PROPAGATION_MINUTES)
        now = datetime.now(timezone.utc)
        if not force and now < ready_at:
            remaining = int((ready_at - now).total_seconds() // 60) + 1
            raise ConflictError(
                detail=(
                    f"La clave pendiente aún no completa su ventana de propagación: faltan {remaining} min. "
                    "Los verificadores con el JWKS cacheado todavía no la tienen."
                )
            )

        if not self.repo.promote(pending):
            # Otra promoción concurrente ya la reclamó (el UPDATE condicional afectó 0 filas).
            raise ConflictError(detail="La clave pendiente ya fue promovida por otra operación")
        self.purge_expired_keys()
        self.session.refresh(pending)
        return pending

    def purge_expired_keys(self) -> int:
        """Borra las claves retiradas que ya no pueden estar firmando ningún token
        vigente (`key_retirement_overlap_minutes`: la vida máxima de token firmado +
        skew). Pasada esa ventana solo agregan ruido al JWKS."""
        from app.core.config import settings

        cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.key_retirement_overlap_minutes)
        return self.repo.purge_retired_before(cutoff)

    # --- Emisión de tokens de sesión interna -------------------------------
    # Tokens del panel/login y del Dev Kit. Se firman con la clave activa (RS256),
    # igual que los tokens de consumidores: un solo mecanismo de firma.

    def issue_session_token(
        self,
        user_id: str,
        email: str,
        name: str,
        application_slug: str = "minerva",
        roles: list[str] | None = None,
        permissions: list[str] | None = None,
    ) -> str:
        kid, private_pem = self.get_active_private_pem()
        return create_access_token_rs256(
            user_id=user_id,
            email=email,
            name=name,
            kid=kid,
            private_key_pem=private_pem,
            application_slug=application_slug,
            roles=roles,
            permissions=permissions,
            typ="session",
        )

    def issue_dev_token(
        self,
        user_id: str,
        email: str,
        name: str,
        applications: list[str] | None = None,
        roles_by_application: dict[str, list[str]] | None = None,
    ) -> str:
        kid, private_pem = self.get_active_private_pem()
        return create_dev_token_rs256(
            user_id=user_id,
            email=email,
            name=name,
            kid=kid,
            private_key_pem=private_pem,
            applications=applications,
            roles_by_application=roles_by_application,
        )
