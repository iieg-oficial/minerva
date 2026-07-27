import base64
import hashlib
import re
import secrets
import uuid
from datetime import datetime, timezone

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

_CODE_VERIFIER_RE = re.compile(r"^[A-Za-z0-9\-._~]{43,128}$")


def hash_token(token: str) -> str:
    """Hash SHA-256 de un token de alta entropía (refresh token), para guardarlo
    en BD sin almacenar el valor en claro. El lookup se hace por este hash."""
    return hashlib.sha256(token.encode()).hexdigest()


def verify_pkce(code_verifier: str, code_challenge: str) -> bool:
    """Verifica un par PKCE con método S256 (RFC 7636).

    challenge == BASE64URL-SIN-PADDING(SHA256(verifier)). Comparación en tiempo
    constante para no filtrar información por temporización. El verifier debe
    cumplir el alfabeto "unreserved" de 43-128 caracteres (RFC 7636 §4.1): fuera
    de eso se rechaza aquí para no llegar al encode('ascii') con datos inválidos.
    """
    if not _CODE_VERIFIER_RE.fullmatch(code_verifier):
        return False
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
    scope: str = "",
    email_verified: bool = False,
    typ: str = "access",
    auth_time: int | None = None,
) -> str:
    """Access token firmado con RS256. Incluye `jti` para revocación (blacklist).

    `jti` puede inyectarse para vincular el token a un refresh token; si se omite,
    se genera uno. `expires_minutes` permite un TTL distinto al de la sesión interna.
    `scope` queda registrado en el token (el canje OIDC lo usa; los tokens de sesión
    interna del panel no lo pasan y quedan con `scope=""`) para que `/userinfo`
    pueda filtrar los claims de identidad por scope sin volver a consultar la BD.
    `typ` marca la clase de token (`session` para el panel, `access` para el canje
    OIDC de consumidores) para que cada endpoint rechace tokens de otra clase (R2).
    `auth_time` fija el instante de autenticación DE ESTA sesión: viaja en el token
    (no en la fila del usuario) porque es propio de cada navegador, y se conserva al
    reemitirlo en `/auth/refresh`.
    """
    now = datetime.now(timezone.utc)
    minutes = expires_minutes if expires_minutes is not None else settings.effective_token_expire_minutes
    payload = {
        "sub": str(user_id),
        "email": email,
        "name": name,
        "email_verified": email_verified,
        "typ": typ,
        "iss": settings.effective_jwt_issuer,
        "aud": application_slug or "minerva",
        "roles": roles or [],
        "permissions": permissions or [],
        "scope": scope,
        "jti": jti or uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int(now.timestamp()) + (minutes * 60),
    }
    if auth_time is not None:
        payload["auth_time"] = auth_time
    return jwt.encode(payload, private_key_pem, algorithm="RS256", headers={"kid": kid})


def create_id_token(
    user_id: str,
    client_id: str,
    kid: str,
    private_key_pem: str,
    claims: dict | None = None,
    nonce: str | None = None,
    auth_time: int | None = None,
    expires_minutes: int | None = None,
) -> str:
    """ID Token OIDC (identidad). `aud` = `client_id` (distinto del access token).

    Lleva claims de identidad puros, sin permisos: el ID Token es para el cliente,
    el access token es para los recursos. `claims` se filtra por scope antes de
    llegar aquí (ver `claims_for_scopes` en `app/modules/oidc/service.py`).
    """
    now = datetime.now(timezone.utc)
    minutes = expires_minutes if expires_minutes is not None else settings.effective_token_expire_minutes
    payload = {
        "sub": str(user_id),
        "typ": "id",
        "iss": settings.effective_jwt_issuer,
        "aud": client_id,
        "iat": int(now.timestamp()),
        "exp": int(now.timestamp()) + (minutes * 60),
    }
    payload.update(claims or {})
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
        "typ": "dev",
        "applications": applications or [],
        "roles": roles_by_application or {},
        "jti": uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int(now.timestamp()) + (minutes * 60),
    }
    return jwt.encode(payload, private_key_pem, algorithm="RS256", headers={"kid": kid})


def decode_token_rs256(token: str, jwks: dict, audience: str | None = None, issuer: str | None = None) -> dict:
    """Valida un JWT RS256 contra un JWKS, seleccionando la clave por `kid`.

    `verify_aud`/`verify_iss` se activan al pasar `audience`/`issuer`. El backend
    verifica siempre el `iss` (ver `dependencies/auth._resolve_token`); el `aud` se
    verifica en los endpoints que conocen su audiencia esperada.
    """
    try:
        return jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            audience=audience,
            issuer=issuer,
            options={"verify_aud": audience is not None, "verify_iss": issuer is not None},
        )
    except JWTError:
        raise ValueError("Token inválido o expirado")
