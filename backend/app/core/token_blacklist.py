"""Blacklist de access tokens por `jti`, en Redis.

Permite revocar un access token (corto) antes de su expiración: al revocar o
rotar un refresh token se invalidan los `jti` de los access tokens asociados.
La entrada vive solo hasta que el token habría expirado (TTL), porque después
ya no sirve de nada guardarla.

La aplicación de esta blacklist en los consumidores se hace en el SDK (Fase 7),
que es quien valida los access tokens RS256.
"""

import time

from redis.asyncio import Redis

_PREFIX = "minerva:blacklist:"
# Marcador por usuario: los tokens con `iat` anterior a este epoch quedan
# invalidados (cambio de contraseña/correo/status). Ver `user_tokens_invalid_before`.
_USER_INVAL_PREFIX = "minerva:uinval:"


async def revoke_jti(redis: Redis, jti: str | None, ttl_seconds: int) -> None:
    if not jti:
        return
    await redis.set(f"{_PREFIX}{jti}", "1", ex=max(ttl_seconds, 1))


async def is_revoked(redis: Redis, jti: str | None) -> bool:
    if not jti:
        return False
    return bool(await redis.exists(f"{_PREFIX}{jti}"))


async def invalidate_user_tokens(redis: Redis, sub: str | None, ttl_seconds: int) -> None:
    """Invalida todos los tokens del usuario emitidos hasta ahora: guarda el epoch
    actual como corte. `_resolve_token` rechaza los tokens cuyo `iat` sea anterior.
    El TTL debe cubrir la vida del token más largo (la sesión del panel, 8h); pasado
    ese punto ya no hay tokens vivos que invalidar y el marcador puede expirar."""
    if not sub:
        return
    await redis.set(f"{_USER_INVAL_PREFIX}{sub}", str(int(time.time())), ex=max(ttl_seconds, 1))


async def user_tokens_invalid_before(redis: Redis, sub: str | None) -> int | None:
    """Epoch de corte para el usuario, o None si no hay invalidación vigente."""
    if not sub:
        return None
    value = await redis.get(f"{_USER_INVAL_PREFIX}{sub}")
    return int(value) if value is not None else None
