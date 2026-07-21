"""Helpers de integración con FastAPI para validar identidad y permisos
emitidos por Minerva.

El flujo recomendado (ver `docs/integracion.md`) es validar **permisos**, no roles.
La firma de los access tokens se verifica con
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

# Caché de permisos ligada al TOKEN, no al usuario:
# { (jti, application_code): (expira_en, permisos) }
_permissions_cache: dict[tuple[str, str], tuple[float, frozenset[str]]] = {}
# Cota del dict antes de barrer las entradas vencidas (ver _prune_permissions_cache).
_PERMISSIONS_CACHE_MAX = 1000
# Caché del JWKS: las claves públicas cambian poco (rotación), no hace falta
# pedirlas en cada request. `retry_after` acota los refrescos por `kid` desconocido.
_jwks_cache: dict[str, object] = {"exp": 0.0, "jwks": None, "retry_after": 0.0}


def _has_kid(jwks: dict, kid: str) -> bool:
    return any(key.get("kid") == kid for key in jwks.get("keys", []))


async def _get_jwks(kid: str | None = None) -> dict:
    """JWKS de Minerva, cacheado. Si el `kid` del token no está en el caché, lo
    refresca aunque no haya expirado: es lo que evita rechazar tokens válidos durante
    una hora tras una rotación de clave en Minerva.

    El refresco se limita a uno por `MINERVA_JWKS_REFRESH_COOLDOWN`, para que tokens
    con un `kid` inventado no conviertan cada request en una llamada a Minerva.
    """
    now = time.time()
    cached = _jwks_cache["jwks"]
    if cached is not None and float(_jwks_cache["exp"]) > now:
        if kid is None or _has_kid(cached, kid):  # type: ignore[arg-type]
            return cached  # type: ignore[return-value]
        if now < float(_jwks_cache["retry_after"]):
            return cached  # type: ignore[return-value]
        _jwks_cache["retry_after"] = now + settings.jwks_refresh_cooldown

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
        header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Token inválido: {exc}")
    alg = header.get("alg")

    # El algoritmo se fija a RS256 (único soportado) para evitar ataques de
    # confusión de algoritmo. No hay validación HS256.
    if alg != "RS256":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Algoritmo de token no soportado: {alg}")

    # La audiencia es obligatoria (= código de esta app): sin ella no se puede
    # verificar que el token fue emitido para este consumidor. No hay switch para
    # desactivarla; si falta la configuración, es un error de despliegue.
    if not settings.application_code:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "MINERVA_APPLICATION_CODE no configurado",
        )

    try:
        jwks = await _get_jwks(kid=header.get("kid"))
        payload = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            audience=settings.application_code,
            options={"verify_aud": True},
        )
    except JWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Token inválido: {exc}")
    except httpx.HTTPError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"No se pudo obtener el JWKS de Minerva: {exc}")

    # El `iss` se valida SIEMPRE: contra MINERVA_EXPECTED_ISSUER o, por defecto, el
    # issuer_url del que se descubre el JWKS. No se puede desactivar.
    expected_iss = (settings.expected_issuer or settings.issuer_url).rstrip("/")
    if str(payload.get("iss", "")).rstrip("/") != expected_iss:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Issuer inválido")

    # Un consumidor solo acepta access tokens (typ=access). Una sesión de panel, un
    # dev token o un id token no cruzan aquí aunque su firma sea válida (RFC 8725).
    if payload.get("typ") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Tipo de token no válido para un consumidor")
    return payload


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """Devuelve los claims del usuario autenticado (valida firma del JWT).

    El dict son **solo** los claims del token: nunca la credencial. Es seguro
    serializarlo o registrarlo en logs. El bearer que `require_permission` necesita
    para consultar Minerva lo obtiene por su cuenta de la misma dependencia
    `_bearer`, no de aquí."""
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token no proporcionado")
    return await _decode(credentials.credentials)


def invalidate_token(jti: str) -> None:
    """Olvida los permisos cacheados de un token concreto. Engánchalo a tu propio
    logout si quieres que la revocación surta efecto sin esperar al TTL."""
    for key in [k for k in _permissions_cache if k[0] == jti]:
        _permissions_cache.pop(key, None)


def clear_caches() -> None:
    """Vacía las cachés en memoria (permisos y JWKS). Pensado para pruebas y para
    forzar una resincronización completa con Minerva."""
    _permissions_cache.clear()
    _jwks_cache["jwks"] = None
    _jwks_cache["exp"] = 0.0
    _jwks_cache["retry_after"] = 0.0


def _prune_permissions_cache(now: float) -> None:
    """Barrido perezoso de entradas vencidas: el dict es global del proceso y sin esto
    crece sin cota en un servicio de larga vida."""
    if len(_permissions_cache) <= _PERMISSIONS_CACHE_MAX:
        return
    for key in [k for k, (expires_at, _) in _permissions_cache.items() if expires_at <= now]:
        _permissions_cache.pop(key, None)


async def _fetch_permissions(token: str, claims: dict, application_code: str) -> set[str]:
    """Permisos del usuario en la aplicación, con caché ligada al TOKEN.

    La caché se indexa por `jti`, no por `sub`: dos tokens del mismo usuario nunca
    comparten una decisión de autorización, así que revocar uno no deja al otro
    heredando permisos (ni al revés). Además la entrada nunca sobrevive al `exp` del
    token que la produjo. Un token sin `jti` no se cachea: se pregunta siempre.
    """
    jti = claims.get("jti")
    now = time.time()
    cache_key = (jti, application_code) if jti else None

    if cache_key is not None:
        cached = _permissions_cache.get(cache_key)
        if cached and cached[0] > now:
            return set(cached[1])

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
            # Minerva ya no reconoce este token: tirar su entrada evita que un
            # reintento dentro del TTL siga viendo permisos cacheados.
            if cache_key is not None:
                _permissions_cache.pop(cache_key, None)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido o revocado")
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"No se pudo consultar permisos en Minerva: {exc}",
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"No se pudo consultar permisos en Minerva: {exc}",
        )

    perms = set(resp.json().get("permissions", []))
    if cache_key is not None:
        # El TTL nunca puede pasar del `exp` del token: una entrada que sobreviviera
        # al token seguiría autorizando a un portador que ya no debería pasar.
        expires_at = now + settings.permissions_cache_ttl
        token_exp = claims.get("exp")
        if token_exp is not None:
            expires_at = min(expires_at, float(token_exp))
        _permissions_cache[cache_key] = (expires_at, frozenset(perms))
        _prune_permissions_cache(now)
    return perms


def require_permission(permission: str, application_code: str | None = None):
    """Dependencia de FastAPI que exige un permiso concreto.

    El permiso se valida contra Minerva en tiempo real (con caché). Si el
    usuario no lo tiene, responde 403.
    """
    app_code = application_code or settings.application_code

    async def dependency(
        user: dict = Depends(get_current_user),
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    ) -> dict:
        if not app_code:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "MINERVA_APPLICATION_CODE no configurado",
            )
        # FastAPI cachea `_bearer` por request: es el mismo objeto que ya validó
        # `get_current_user`, así que llegar aquí garantiza que no es None.
        assert credentials is not None
        perms = await _fetch_permissions(credentials.credentials, user, app_code)
        if permission not in perms:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requiere permiso: {permission}")
        return user

    return dependency
