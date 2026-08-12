import json

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from redis.asyncio import Redis
from sqlmodel import Session

from app.core import panel_session
from app.core.config import settings
from app.core.dependencies.db import get_db
from app.core.exceptions import BearerUnauthorizedError, UnauthorizedError
from app.core.redis import get_redis
from app.core.security import decode_token_rs256
from app.core.token_blacklist import is_revoked, user_tokens_invalid_before

bearer_scheme = HTTPBearer(auto_error=False)

JWKS_CACHE_KEY = "minerva:jwks:current"
JWKS_REFRESH_COOLDOWN_KEY = "minerva:jwks:refresh"
JWKS_REFRESH_COOLDOWN_SECONDS = 10


async def invalidate_jwks_cache(redis: Redis) -> None:
    """Borra el JWKS cacheado. Lo llama el CLI tras publicar o promover una clave:
    sin esto el backend seguiría sirviendo el JWKS viejo hasta que expire el TTL y
    rechazaría tokens que él mismo acaba de firmar."""
    await redis.delete(JWKS_CACHE_KEY)


async def _refresh_allowed(redis: Redis) -> bool:
    """Cooldown del refresco por `kid` desconocido. El JWKS se sirve en endpoints sin
    autenticar: sin esto, tokens con un `kid` inventado reconstruirían el JWKS desde BD
    en cada request. `SET NX` deja pasar el primero de cada ventana y bloquea el resto."""
    return bool(await redis.set(JWKS_REFRESH_COOLDOWN_KEY, "1", ex=JWKS_REFRESH_COOLDOWN_SECONDS, nx=True))


async def _get_jwks_cached(session: Session, redis: Redis, kid: str | None = None) -> dict:
    """Cachea el JWKS en Redis con TTL corto para no reconstruirlo desde BD en
    cada request. `OIDCService` es puramente síncrona (sobre `Session`); el caché
    vive aquí, no ahí, para no mezclarla con Redis async.

    Si el `kid` del token no está en el JWKS cacheado, lo reconstruye desde BD: un
    caché viejo tras una rotación haría rechazar tokens que el propio backend acaba de
    firmar. Es la red de seguridad de la invalidación explícita del CLI — con esto, un
    caché stale nunca produce un 401 espurio, aunque Redis no se haya podido limpiar."""
    # Import diferido para no acoplar la capa core con el módulo oidc.
    from app.modules.oidc.service import OIDCService

    cached = await redis.get(JWKS_CACHE_KEY)
    if cached is not None:
        jwks = json.loads(cached)
        if kid is None or any(key.get("kid") == kid for key in jwks.get("keys", [])):
            return jwks
        if not await _refresh_allowed(redis):
            return jwks
    jwks = OIDCService(session).build_jwks()
    await redis.set(JWKS_CACHE_KEY, json.dumps(jwks), ex=settings.MINERVA_JWKS_CACHE_TTL_SECONDS)
    return jwks


def _unverified_kid(token: str) -> str | None:
    """`kid` del header, sin verificar firma: solo sirve para elegir con qué JWKS
    intentar la validación. Un token ilegible devuelve None y falla en el decode real."""
    try:
        return jwt.get_unverified_header(token).get("kid")
    except JWTError:
        return None


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
    jwks = await _get_jwks_cached(session, redis, kid=_unverified_kid(token))
    payload = decode_token_rs256(token, jwks, audience=audience, issuer=settings.effective_jwt_issuer)
    if expected_types is not None and payload.get("typ") not in expected_types:
        raise ValueError("Tipo de token no válido para esta operación")
    if await is_revoked(redis, payload.get("jti")):
        raise ValueError("Token revocado")
    # Invalidación por usuario: si cambió su contraseña/correo/status, los tokens
    # emitidos hasta el corte (inclusive) dejan de valer aunque su firma siga siendo
    # válida. El corte es un epoch en segundos: uno emitido en su mismo segundo debe
    # invalidarse también, no solo los estrictamente anteriores.
    cutoff = await user_tokens_invalid_before(redis, payload.get("sub"))
    if cutoff is not None and payload.get("iat", 0) <= cutoff:
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
            # Sin credencial: challenge sin código de error (RFC 6750 §3.1).
            raise BearerUnauthorizedError(detail="Token no proporcionado")
        try:
            return await _resolve_token(
                credentials.credentials, session, redis, expected_types=expected_types, audience=audience
            )
        except ValueError as e:
            if optional:
                return None
            raise BearerUnauthorizedError(detail=str(e), error="invalid_token")

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
