from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlmodel import Session

from app.core.dependencies.db import get_db
from app.core.exceptions import UnauthorizedError
from app.core.redis import get_redis
from app.core.security import decode_token, decode_token_rs256, unverified_alg
from app.core.token_blacklist import is_revoked

bearer_scheme = HTTPBearer(auto_error=False)


async def _resolve_token(token: str, session: Session, redis: Redis) -> dict:
    """Valida el token según su algoritmo.

    - RS256: token de consumidor; se verifica contra el JWKS local (clave activa +
      retiradas) y se rechaza si su `jti` está en la blacklist (revocado).
    - HS256: token interno de sesión (login del panel); secreto compartido.
    """
    if unverified_alg(token) == "RS256":
        # Import diferido para no acoplar la capa core con el módulo oidc.
        from app.modules.oidc.service import OIDCService

        jwks = OIDCService(session).build_jwks()
        payload = decode_token_rs256(token, jwks)
        if await is_revoked(redis, payload.get("jti")):
            raise ValueError("Token revocado")
        return payload
    return decode_token(token)


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
