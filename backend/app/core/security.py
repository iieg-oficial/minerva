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
