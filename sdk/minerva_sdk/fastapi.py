"""Helpers de integración con FastAPI para validar identidad y permisos
emitidos por Minerva.

El flujo recomendado (ver `docs/minerva-dev-kit-context.md`, secciones 4 y 13)
es validar **permisos**, no roles. Los permisos finos se consultan en tiempo
real al endpoint `GET /api/v1/me/permissions` de Minerva, con una pequeña
caché en memoria para no consultar en cada request.
"""
import time

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from minerva_sdk.config import settings

_bearer = HTTPBearer(auto_error=False)

# Caché simple: { (sub, application_code): (expira_en, set_de_permisos) }
_permissions_cache: dict[tuple[str, str], tuple[float, set[str]]] = {}


def _decode(token: str) -> dict:
    try:
        options = {"verify_aud": False, "verify_signature": settings.verify_signature}
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options=options,
        )
    except JWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Token inválido: {exc}")

    if settings.expected_issuer and payload.get("iss") != settings.expected_issuer:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Issuer inválido")
    return payload


def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> dict:
    """Devuelve los claims del usuario autenticado (valida firma del JWT)."""
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token no proporcionado")
    user = _decode(credentials.credentials)
    user["_token"] = credentials.credentials
    return user


def _fetch_permissions(token: str, sub: str, application_code: str) -> set[str]:
    cache_key = (sub, application_code)
    now = time.time()
    cached = _permissions_cache.get(cache_key)
    if cached and cached[0] > now:
        return cached[1]

    url = f"{settings.issuer_url.rstrip('/')}/api/v1/me/permissions"
    try:
        resp = httpx.get(
            url,
            params={"application": application_code},
            headers={"Authorization": f"Bearer {token}"},
            timeout=10.0,
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"No se pudo consultar permisos en Minerva: {exc}")

    perms = set(resp.json().get("permissions", []))
    _permissions_cache[cache_key] = (now + settings.permissions_cache_ttl, perms)
    return perms


def require_permission(permission: str, application_code: str | None = None):
    """Dependencia de FastAPI que exige un permiso concreto.

    El permiso se valida contra Minerva en tiempo real (con caché). Si el
    usuario no lo tiene, responde 403.
    """
    app_code = application_code or settings.application_code

    def dependency(user: dict = Depends(get_current_user)) -> dict:
        if not app_code:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "MINERVA_APPLICATION_CODE no configurado",
            )
        perms = _fetch_permissions(user["_token"], user["sub"], app_code)
        if permission not in perms:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requiere permiso: {permission}")
        return user

    return dependency
