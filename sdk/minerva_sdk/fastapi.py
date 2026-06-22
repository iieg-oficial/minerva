"""Helpers de integración con FastAPI para validar identidad y permisos
emitidos por Minerva.

El flujo recomendado (ver `docs/minerva-dev-kit-context.md`, secciones 4 y 13)
es validar **permisos**, no roles. La firma de los access tokens se verifica con
RS256 contra el JWKS público de Minerva (sin secreto compartido). Los permisos
finos se consultan en tiempo real a `GET /api/v1/me/permissions`, con caché en
memoria; ese endpoint también aplica la revocación del lado de Minerva, así que
un token revocado deja de pasar los chequeos de permiso.
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
# Caché del JWKS: las claves públicas cambian poco (rotación), no hace falta
# pedirlas en cada request.
_jwks_cache: dict[str, object] = {"exp": 0.0, "jwks": None}


async def _get_jwks() -> dict:
    now = time.time()
    cached = _jwks_cache["jwks"]
    if cached is not None and float(_jwks_cache["exp"]) > now:
        return cached  # type: ignore[return-value]

    url = f"{settings.issuer_url.rstrip('/')}/.well-known/jwks.json"
    async with httpx.AsyncClient(timeout=settings.request_timeout) as cli:
        resp = await cli.get(url)
        resp.raise_for_status()
    jwks = resp.json()
    _jwks_cache["jwks"] = jwks
    _jwks_cache["exp"] = now + settings.jwks_cache_ttl
    return jwks


async def _decode(token: str) -> dict:
    try:
        alg = jwt.get_unverified_header(token).get("alg")
    except JWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Token inválido: {exc}")

    # El algoritmo se fija a RS256 (único soportado) para evitar ataques de
    # confusión de algoritmo. No hay validación HS256.
    if alg != "RS256":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Algoritmo de token no soportado: {alg}")

    # El audience esperado es el código de esta aplicación (= aud del access token).
    audience = settings.application_code if (settings.verify_aud and settings.application_code) else None

    try:
        jwks = await _get_jwks()
        payload = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            audience=audience,
            options={"verify_aud": audience is not None},
        )
    except JWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Token inválido: {exc}")
    except httpx.HTTPError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"No se pudo obtener el JWKS de Minerva: {exc}")

    if settings.expected_issuer and payload.get("iss") != settings.expected_issuer:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Issuer inválido")
    return payload


async def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> dict:
    """Devuelve los claims del usuario autenticado (valida firma del JWT)."""
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token no proporcionado")
    user = await _decode(credentials.credentials)
    user["_token"] = credentials.credentials
    return user


async def _fetch_permissions(token: str, sub: str, application_code: str) -> set[str]:
    cache_key = (sub, application_code)
    now = time.time()
    cached = _permissions_cache.get(cache_key)
    if cached and cached[0] > now:
        return cached[1]

    url = f"{settings.issuer_url.rstrip('/')}/api/v1/me/permissions"
    try:
        async with httpx.AsyncClient(timeout=settings.request_timeout) as cli:
            resp = await cli.get(
                url,
                params={"application": application_code},
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        # 401 de Minerva (p. ej. token revocado) se propaga como 401 al cliente.
        if exc.response.status_code == status.HTTP_401_UNAUTHORIZED:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido o revocado")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"No se pudo consultar permisos en Minerva: {exc}")
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

    async def dependency(user: dict = Depends(get_current_user)) -> dict:
        if not app_code:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "MINERVA_APPLICATION_CODE no configurado",
            )
        perms = await _fetch_permissions(user["_token"], user["sub"], app_code)
        if permission not in perms:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requiere permiso: {permission}")
        return user

    return dependency
