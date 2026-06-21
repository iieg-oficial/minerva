import uuid
from datetime import datetime, timezone

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())


def hash_secret(secret: str) -> str:
    return bcrypt.hashpw(secret.encode(), bcrypt.gensalt()).decode()


def verify_secret(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(
    user_id: str,
    email: str,
    name: str,
    application_slug: str = "",
    roles: list[str] | None = None,
    permissions: list[str] | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "email": email,
        "name": name,
        "iss": settings.effective_jwt_issuer,
        "aud": application_slug or "minerva",
        "roles": roles or [],
        "permissions": permissions or [],
        "iat": int(now.timestamp()),
        "exp": int(now.timestamp()) + (settings.effective_token_expire_minutes * 60),
    }
    return jwt.encode(payload, settings.effective_jwt_secret, algorithm=settings.JWT_ALGORITHM)


def create_dev_token(
    user_id: str,
    email: str,
    name: str,
    applications: list[str] | None = None,
    roles_by_application: dict[str, list[str]] | None = None,
) -> str:
    """Token de desarrollo del Minerva Dev Kit.

    Sigue los claims sugeridos en el documento de contexto (sección 11):
    incluye la lista de `applications` y un mapa `roles` por aplicación.
    Los permisos finos se consultan vía `GET /api/v1/me/permissions`.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "iss": settings.effective_jwt_issuer,
        "sub": str(user_id),
        "email": email,
        "name": name,
        "applications": applications or [],
        "roles": roles_by_application or {},
        "iat": int(now.timestamp()),
        "exp": int(now.timestamp()) + (settings.effective_token_expire_minutes * 60),
    }
    return jwt.encode(payload, settings.effective_jwt_secret, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.effective_jwt_secret,
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_aud": False},
        )
        return payload
    except JWTError:
        raise ValueError("Token inválido o expirado")


# --- RS256 / OIDC ----------------------------------------------------------
# Firma asimétrica (clave privada RSA) con `kid` en el header, para que los
# consumidores verifiquen vía JWKS sin compartir secreto. Convive con HS256
# durante la transición.


def create_access_token_rs256(
    user_id: str,
    email: str,
    name: str,
    kid: str,
    private_key_pem: str,
    application_slug: str = "",
    roles: list[str] | None = None,
    permissions: list[str] | None = None,
) -> str:
    """Access token firmado con RS256. Incluye `jti` para revocación (blacklist)."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "email": email,
        "name": name,
        "iss": settings.effective_jwt_issuer,
        "aud": application_slug or "minerva",
        "roles": roles or [],
        "permissions": permissions or [],
        "jti": uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int(now.timestamp()) + (settings.effective_token_expire_minutes * 60),
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
) -> str:
    """ID Token OIDC (identidad). `aud` = `client_id` (distinto del access token).

    Lleva claims de identidad puros, sin permisos: el ID Token es para el cliente,
    el access token es para los recursos.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iss": settings.effective_jwt_issuer,
        "aud": client_id,
        "email": email,
        "name": name,
        "iat": int(now.timestamp()),
        "exp": int(now.timestamp()) + (settings.effective_token_expire_minutes * 60),
    }
    if nonce is not None:
        payload["nonce"] = nonce
    if auth_time is not None:
        payload["auth_time"] = auth_time
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
