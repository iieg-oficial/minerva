import uuid

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwk
from sqlmodel import Session

from app.core.crypto import decrypt_secret, encrypt_secret
from app.core.exceptions import AppException
from app.core.security import create_access_token_rs256, create_dev_token_rs256
from app.modules.oidc.models import SigningKey
from app.modules.oidc.repository import SigningKeyRepository


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

    def generate_signing_key(self) -> SigningKey:
        """Genera un par RSA nuevo, cifra la clave privada y lo persiste como activo."""
        private_pem, public_pem = _generate_rsa_keypair()
        key = SigningKey(
            kid=uuid.uuid4().hex,
            algorithm="RS256",
            private_key_pem=encrypt_secret(private_pem),
            public_key_pem=public_pem,
            status="active",
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

    def rotate_key(self) -> SigningKey:
        """Retira la clave activa actual y genera una nueva activa."""
        current = self.repo.get_active()
        if current is not None:
            self.repo.mark_retired(current)
        return self.generate_signing_key()

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
