"""Rate limiting con Redis (ventana deslizante sobre sorted sets).

Se usa en endpoints sensibles (`/auth/login`, `/auth/authorize`) para frenar
fuerza bruta y abuso. Es async porque habla con Redis; los handlers que lo usan
deben ser `async def`.

Por qué Redis y no PostgreSQL: son contadores de altísima frecuencia con
expiración atómica; en PG requeriría SELECT FOR UPDATE + limpieza por cron.
"""

import time
import uuid

from redis.asyncio import Redis

from app.core.exceptions import TooManyRequestsError


async def check_rate_limit(redis: Redis, key: str, max_requests: int, window: int) -> bool:
    """Ventana deslizante con sorted set. Registra el intento actual y cuenta los
    intentos dentro de la ventana.

    Retorna True si se puede proceder, False si se excedió el límite.
    """
    now = time.time()
    member = f"{now}-{uuid.uuid4().hex}"  # único: evita colisiones de score idénticos
    pipe = redis.pipeline()
    pipe.zremrangebyscore(key, 0, now - window)  # purga lo más viejo que la ventana
    pipe.zadd(key, {member: now})
    pipe.zcard(key)
    pipe.expire(key, window)
    _, _, count, _ = await pipe.execute()
    return count <= max_requests


async def enforce_rate_limit(redis: Redis, key: str, max_requests: int, window: int) -> None:
    """Igual que `check_rate_limit` pero lanza 429 con `Retry-After` si se excede."""
    allowed = await check_rate_limit(redis, key, max_requests, window)
    if not allowed:
        raise TooManyRequestsError(retry_after=window)


# --- Contador de fallos ------------------------------------------------------
# A diferencia de `check_rate_limit`, que cuenta toda petición, estos helpers solo
# registran intentos fallidos: el límite por cuenta del login no debe consumirse con
# los ingresos correctos, y un éxito lo limpia.


async def enforce_failure_limit(redis: Redis, key: str, max_failures: int, window: int) -> None:
    """Rechaza con 429 si la clave ya acumula `max_failures` fallos en la ventana. No
    registra nada: el fallo se anota después con `record_failure`, cuando se sabe.

    `Retry-After` es lo que falta para que el fallo más viejo salga de la ventana, que es
    cuando se vuelve a admitir un intento."""
    now = time.time()
    pipe = redis.pipeline()
    pipe.zremrangebyscore(key, 0, now - window)
    pipe.zcard(key)
    pipe.zrange(key, 0, 0, withscores=True)
    _, count, oldest = await pipe.execute()
    if count < max_failures:
        return
    retry_after = int(oldest[0][1] + window - now) + 1 if oldest else window
    raise TooManyRequestsError(retry_after=max(retry_after, 1))


async def record_failure(redis: Redis, key: str, window: int) -> None:
    now = time.time()
    pipe = redis.pipeline()
    pipe.zadd(key, {f"{now}-{uuid.uuid4().hex}": now})
    pipe.expire(key, window)
    await pipe.execute()


async def clear_failures(redis: Redis, key: str) -> None:
    await redis.delete(key)
