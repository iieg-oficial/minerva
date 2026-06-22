"""Blacklist de access tokens por `jti`, en Redis.

Permite revocar un access token (corto) antes de su expiración: al revocar o
rotar un refresh token se invalidan los `jti` de los access tokens asociados.
La entrada vive solo hasta que el token habría expirado (TTL), porque después
ya no sirve de nada guardarla.

La aplicación de esta blacklist en los consumidores se hace en el SDK (Fase 7),
que es quien valida los access tokens RS256.
"""

from redis.asyncio import Redis

_PREFIX = "minerva:blacklist:"


async def revoke_jti(redis: Redis, jti: str | None, ttl_seconds: int) -> None:
    if not jti:
        return
    await redis.set(f"{_PREFIX}{jti}", "1", ex=max(ttl_seconds, 1))


async def is_revoked(redis: Redis, jti: str | None) -> bool:
    if not jti:
        return False
    return bool(await redis.exists(f"{_PREFIX}{jti}"))
