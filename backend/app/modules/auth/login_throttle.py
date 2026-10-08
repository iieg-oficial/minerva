"""Límite de intentos del login por cuenta.

El límite por IP no alcanza para frenar fuerza bruta: la IP se puede disfrazar si algún
salto confía de más en `X-Forwarded-For`, y detrás de un WAF que no la propaga todos los
usuarios comparten una sola. Este contador va por cuenta —el correo normalizado— y solo
suma intentos fallidos: tras `RATE_LIMIT_LOGIN_MAX` fallos en la ventana, esa cuenta
responde 429 con `Retry-After` hasta que el fallo más viejo expire. Un login exitoso lo
limpia.

La clave se calcula igual exista o no la cuenta, así que el límite no revela cuáles
existen: una cuenta inexistente se bloquea con la misma respuesta que una real.
"""

import hashlib

from redis.asyncio import Redis

from app.core.config import settings
from app.core.rate_limit import clear_failures, enforce_failure_limit, record_failure
from app.modules.users.repository import normalize_email

_PREFIX = "minerva:rl:login-account:"


def account_key(email: str) -> str:
    """Hasheada para que el correo no quede en claro en las claves de Redis."""
    return f"{_PREFIX}{hashlib.sha256(normalize_email(email).encode()).hexdigest()}"


async def enforce(redis: Redis, email: str) -> None:
    await enforce_failure_limit(
        redis, account_key(email), settings.RATE_LIMIT_LOGIN_MAX, settings.RATE_LIMIT_LOGIN_WINDOW
    )


async def record(redis: Redis, email: str) -> None:
    await record_failure(redis, account_key(email), settings.RATE_LIMIT_LOGIN_WINDOW)


async def clear(redis: Redis, email: str) -> None:
    await clear_failures(redis, account_key(email))
