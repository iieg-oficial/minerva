"""Cliente Redis async compartido.

Redis es también un **control de seguridad**, no solo caché: rate limiting, blacklist
de `jti` revocados, cortes de invalidación por usuario y el **contenedor de sesión del
panel** (patrón BFF, `panel_session.py`) — la fuente de verdad efímera del multi-cuenta.
Perder Redis cierra las sesiones del panel y re-habilita tokens revocados; por eso corre con
persistencia AOF (`appendonly yes`) y `noeviction` (ver docker-compose y docs/despliegue.md §3.4),
para sobrevivir reinicios sin desalojar revocaciones. NO es la fuente de verdad de datos
persistentes (eso es PostgreSQL).

Política fail-closed: si Redis no está disponible, `is_revoked`/`user_tokens_invalid_before` y el
rate limit propagan el error y la request se rechaza. No se degrada a fail-open: nunca se honra un
token que no se pudo verificar contra la blacklist.

El cliente es un singleton por proceso. Con Gunicorn cada worker es un proceso
propio y crea su propia instancia; es correcto porque Redis es externo y
compartido entre workers. Se inicializa y cierra en el lifespan de FastAPI.
"""

from redis.asyncio import Redis

from app.core.config import settings

_redis: Redis | None = None


async def init_redis() -> Redis:
    """Crea la conexión compartida. Se llama una vez en el lifespan."""
    global _redis
    if _redis is None:
        _redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


def get_redis() -> Redis:
    """Devuelve el cliente ya inicializado.

    Falla explícitamente si Redis no se inicializó: rate limiting y blacklist
    son operaciones de seguridad y no deben degradarse en silencio.
    """
    if _redis is None:
        raise RuntimeError("Redis no inicializado. ¿Se llamó init_redis() en el lifespan?")
    return _redis


async def close_redis() -> None:
    """Cierra la conexión compartida al apagar el servicio."""
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
