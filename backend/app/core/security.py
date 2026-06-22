import base64
import hashlib
import secrets
import uuid
from datetime import datetime, timezone

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings


def hash_token(token: str) -> str:
    """Hash SHA-256 de un token de alta entropía (refresh token), para guardarlo
    en BD sin almacenar el valor en claro. El lookup se hace por este hash."""
    return hashlib.sha256(token.encode()).hexdigest()


def verify_pkce(code_verifier: str, code_challenge: str) -> bool:
    """Verifica un par PKCE con método S256 (RFC 7636).

    challenge == BASE64URL-SIN-PADDING(SHA256(verifier)). Comparación en tiempo
    constante para no filtrar información por temporización.
    """
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return secrets.compare_digest(expected, code_challenge)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())


def hash_secret(secret: str) -> str:
    return bcrypt.hashpw(secret.encode(), bcrypt.gensalt()).decode()


def verify_secret(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# --- RS256 / OIDC ----------------------------------------------------------
# Toda la firma de tokens es RS256 (clave privada RSA, `kid` en el header). Los
# verificadores (SDK, consumidores y el propio backend) validan vía JWKS sin
# compartir secreto. No hay firma simétrica HS256 en el sistema.


def create_access_token_rs256(
    user_id: str,
    email: str,
    name: str,
    kid: str,
    private_key_pem: str,
    application_slug: str = "",
    roles: list[str] | None = None,
    permissions: list[str] | None = None,
    jti: str | None = None,
    expires_minutes: int | None = None,
) -> str:
    """Access token firmado con RS256. Incluye `jti` para revocación (blacklist).

    `jti` puede inyectarse para vincular el token a un refresh token; si se omite,
    se genera uno. `expires_minutes` permite un TTL distinto al de la sesión interna.
    """
    now = datetime.now(timezone.utc)
    minutes = expires_minutes if expires_minutes is not None else settings.effective_token_expire_minutes
    payload = {
        "sub": str(user_id),
        "email": email,
        "name": name,
        "iss": settings.effective_jwt_issuer,
        "aud": application_slug or "minerva",
        "roles": roles or [],
        "permissions": permissions or [],
        "jti": jti or uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int(now.timestamp()) + (minutes * 60),
    }
    return jwt.encode(payload, private_key_pem, algorithm="RS256", headers={"kid": kid})


def create_id_token(
    user_id: str,
    email: str,
    name: str,
    client_id: str,
    kid: str,
    private_key_pem: str,
    nonce: str | None = None,
    auth_time: int | None = None,
    expires_minutes: int | None = None,
) -> str:
    """ID Token OIDC (identidad). `aud` = `client_id` (distinto del access token).

    Lleva claims de identidad puros, sin permisos: el ID Token es para el cliente,
    el access token es para los recursos.
    """
    now = datetime.now(timezone.utc)
    minutes = expires_minutes if expires_minutes is not None else settings.effective_token_expire_minutes
    payload = {
        "sub": str(user_id),
        "iss": settings.effective_jwt_issuer,
        "aud": client_id,
        "email": email,
        "name": name,
        "iat": int(now.timestamp()),
        "exp": int(now.timestamp()) + (minutes * 60),
    }
    if nonce is not None:
        payload["nonce"] = nonce
    if auth_time is not None:
        payload["auth_time"] = auth_time
    return jwt.encode(payload, private_key_pem, algorithm="RS256", headers={"kid": kid})


def create_dev_token_rs256(
    user_id: str,
    email: str,
    name: str,
    kid: str,
    private_key_pem: str,
    applications: list[str] | None = None,
    roles_by_application: dict[str, list[str]] | None = None,
    expires_minutes: int | None = None,
) -> str:
    """Token de desarrollo del Minerva Dev Kit, firmado con RS256.

    Sigue los claims sugeridos en el documento de contexto (sección 11): incluye
    la lista de `applications` y un mapa `roles` por aplicación. Los permisos
    finos se consultan vía `GET /api/v1/me/permissions`.
    """
    now = datetime.now(timezone.utc)
    minutes = expires_minutes if expires_minutes is not None else settings.effective_token_expire_minutes
    payload = {
        "iss": settings.effective_jwt_issuer,
        "sub": str(user_id),
        "email": email,
        "name": name,
        "applications": applications or [],
        "roles": roles_by_application or {},
        "jti": uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int(now.timestamp()) + (minutes * 60),
    }
    return jwt.encode(payload, private_key_pem, algorithm="RS256", headers={"kid": kid})


def decode_token_rs256(token: str, jwks: dict, audience: str | None = None) -> dict:
    """Valida un JWT RS256 contra un JWKS, seleccionando la clave por `kid`.

    `verify_aud` se mantiene desactivado por defecto durante la transición; se
    activará pasando `audience` cuando el `aud` sea consistente (Fase 4).
    """
    try:
        return jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            audience=audience,
            options={"verify_aud": audience is not None},
        )
    except JWTError:
        raise ValueError("Token inválido o expirado")
