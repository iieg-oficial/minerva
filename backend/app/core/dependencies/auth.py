import json

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlmodel import Session

from app.core.config import settings
from app.core.dependencies.db import get_db
from app.core.exceptions import UnauthorizedError
from app.core.redis import get_redis
from app.core.security import decode_token_rs256
from app.core.token_blacklist import is_revoked, user_tokens_invalid_before

bearer_scheme = HTTPBearer(auto_error=False)

JWKS_CACHE_KEY = "minerva:jwks:current"


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

    `expected_types` restringe la clase de token (`typ`) aceptada por el endpoint:
    sin esto, un access de consumidor (15 min) valía en cualquier endpoint del panel
    (R2). `audience` activa la verificación de `aud` cuando el endpoint la conoce."""
    jwks = await _get_jwks_cached(session, redis)
    payload = decode_token_rs256(token, jwks, audience=audience)
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


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: Session = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict:
    if credentials is None:
        raise UnauthorizedError(detail="Token no proporcionado")
    try:
        return await _resolve_token(credentials.credentials, session, redis)
    except ValueError as e:
        raise UnauthorizedError(detail=str(e))


async def get_current_session_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: Session = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict:
    """Como `get_current_user`, pero solo acepta el token de **sesión del panel**
    (`typ=session`, `aud=minerva`). Protege los endpoints del panel/admin y el
    refresh de sesión: un access de consumidor o un dev token no cruzan aquí (R2)."""
    if credentials is None:
        raise UnauthorizedError(detail="Token no proporcionado")
    try:
        return await _resolve_token(
            credentials.credentials, session, redis, expected_types={"session"}, audience="minerva"
        )
    except ValueError as e:
        raise UnauthorizedError(detail=str(e))


async def get_optional_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: Session = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict | None:
    if credentials is None:
        return None
    try:
        return await _resolve_token(credentials.credentials, session, redis)
    except ValueError:
        return None
