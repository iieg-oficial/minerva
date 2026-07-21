import json

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlmodel import Session

from app.core import panel_session
from app.core.config import settings
from app.core.dependencies.db import get_db
from app.core.exceptions import UnauthorizedError
from app.core.redis import get_redis
from app.core.security import decode_token_rs256
from app.core.token_blacklist import is_revoked, user_tokens_invalid_before

bearer_scheme = HTTPBearer(auto_error=False)

JWKS_CACHE_KEY = "minerva:jwks:current"


async def invalidate_jwks_cache(redis: Redis) -> None:
    """Borra el JWKS cacheado. Lo llama el CLI tras publicar o promover una clave:
    sin esto el backend seguiría sirviendo el JWKS viejo hasta que expire el TTL y
    rechazaría tokens que él mismo acaba de firmar."""
    await redis.delete(JWKS_CACHE_KEY)


async def _get_jwks_cached(session: Session, redis: Redis) -> dict:
    """Cachea el JWKS en Redis con TTL corto para no reconstruirlo desde BD en
    cada request. `OIDCService` es puramente síncrona (sobre `Session`); el caché
    vive aquí, no ahí, para no mezclarla con Redis async."""
    # Import diferido para no acoplar la capa core con el módulo oidc.
    from app.modules.oidc.service import OIDCService

    cached = await redis.get(JWKS_CACHE_KEY)
    if cached is not None:
        return json.loads(cached)
    jwks = OIDCService(session).build_jwks()
    await redis.set(JWKS_CACHE_KEY, json.dumps(jwks), ex=settings.MINERVA_JWKS_CACHE_TTL_SECONDS)
    return jwks


async def _resolve_token(
    token: str,
    session: Session,
    redis: Redis,
    expected_types: set[str] | None = None,
    audience: str | None = None,
) -> dict:
    """Valida un token RS256 contra el JWKS local (clave activa + retiradas) y lo
    rechaza si su `jti` está en la blacklist (revocado). Toda la firma del sistema
    es RS256: tokens de consumidores y de sesión interna del panel.

    Verifica **siempre** el `iss` contra el issuer del sistema. `expected_types`
    restringe la clase de token (`typ`) aceptada por el endpoint: sin esto, un
    access de consumidor (15 min) valía en cualquier endpoint del panel (R2).
    `audience` activa la verificación de `aud` cuando el endpoint la conoce."""
    jwks = await _get_jwks_cached(session, redis)
    payload = decode_token_rs256(token, jwks, audience=audience, issuer=settings.effective_jwt_issuer)
    if expected_types is not None and payload.get("typ") not in expected_types:
        raise ValueError("Tipo de token no válido para esta operación")
    if await is_revoked(redis, payload.get("jti")):
        raise ValueError("Token revocado")
    # Invalidación por usuario: si cambió su contraseña/correo/status, los tokens
    # emitidos antes del corte dejan de valer aunque su firma siga siendo válida.
    cutoff = await user_tokens_invalid_before(redis, payload.get("sub"))
    if cutoff is not None and payload.get("iat", 0) < cutoff:
        raise ValueError("Sesión invalidada; vuelve a iniciar sesión")
    return payload


def _bearer_user_dependency(
    expected_types: set[str] | None,
    audience: str | None = None,
    optional: bool = False,
):
    """Fábrica de dependencias de autenticación por **clase de token**. Cada endpoint
    declara qué `typ` (y opcionalmente qué `aud`) acepta, en vez de compartir una
    dependencia genérica que dejaba cruzar cualquier JWT firmado (R2)."""

    async def dependency(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
        session: Session = Depends(get_db),
        redis: Redis = Depends(get_redis),
    ) -> dict | None:
        if credentials is None:
            if optional:
                return None
            raise UnauthorizedError(detail="Token no proporcionado")
        try:
            return await _resolve_token(
                credentials.credentials, session, redis, expected_types=expected_types, audience=audience
            )
        except ValueError as e:
            if optional:
                return None
            raise UnauthorizedError(detail=str(e))

    return dependency


# Access token de consumidor (`typ=access`). Para `/userinfo`: el `aud` es el código
# de la app y varía por consumidor, así que no se fija aquí (se valida en el SDK).
get_current_access_user = _bearer_user_dependency({"access"})

# Self-service del Dev Kit (`/api/v1/me*`): access de consumidor o dev token.
get_current_devkit_user = _bearer_user_dependency({"access", "dev"})


# --- Sesión del panel por cookie opaca (patrón BFF) ------------------------
# El panel ya NO autentica por Bearer: el token `typ=session` vive en Redis
# (contenedor multi-cuenta) y el navegador solo trae la cookie opaca. La
# validación del JWT sigue siendo `_resolve_token` (firma/iss/aud/typ/jti/corte):
# aquí solo se resuelve QUÉ token usar (el de la cuenta activa del contenedor).


async def _panel_user_from_cookie(request: Request, session: Session, redis: Redis, optional: bool) -> dict | None:
    sid = request.cookies.get(settings.session_cookie_name)
    container = await panel_session.read(redis, sid)
    if container is None:
        if optional:
            return None
        raise UnauthorizedError(detail="Sesión de panel no encontrada")
    token = panel_session.active_token(container)
    if not token:
        if optional:
            return None
        raise UnauthorizedError(detail="No hay una cuenta activa en la sesión")
    try:
        payload = await _resolve_token(token, session, redis, expected_types={"session"}, audience="minerva")
    except ValueError as e:
        if optional:
            return None
        raise UnauthorizedError(detail=str(e))
    payload["sid"] = sid
    return payload


async def get_current_panel_user(
    request: Request,
    session: Session = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict:
    """Usuario de la cuenta activa del contenedor de sesión (cookie opaca). Reemplaza
    al antiguo Bearer `typ=session` en los endpoints del panel/admin."""
    return await _panel_user_from_cookie(request, session, redis, optional=False)


async def get_optional_panel_user(
    request: Request,
    session: Session = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict | None:
    """Variante opcional para `/authorize` (navegación directa del consumidor con la
    cookie de panel presente; sin sesión no falla, deja seguir el flujo a login)."""
    return await _panel_user_from_cookie(request, session, redis, optional=True)


async def get_panel_session(
    request: Request,
    redis: Redis = Depends(get_redis),
) -> dict:
    """Contenedor + sid de la sesión del panel, SIN exigir cuenta activa válida (para
    el selector y los endpoints de logout/gestión de cuentas). No valida el JWT: eso
    lo hacen los endpoints que actúan sobre la cuenta activa."""
    sid = request.cookies.get(settings.session_cookie_name)
    container = await panel_session.read(redis, sid)
    if container is None:
        raise UnauthorizedError(detail="Sesión de panel no encontrada")
    return {"sid": sid, "container": container}
