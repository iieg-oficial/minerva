"""Tests del rate limiting con Redis (ventana deslizante)."""

import fakeredis.aioredis

from app.core.rate_limit import check_rate_limit


async def test_check_rate_limit_allows_until_max_then_blocks():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    key = "minerva:rl:test:1.2.3.4"

    # Los primeros 3 intentos se permiten (max=3).
    for _ in range(3):
        assert await check_rate_limit(redis, key, max_requests=3, window=60) is True

    # El 4to excede el límite.
    assert await check_rate_limit(redis, key, max_requests=3, window=60) is False


async def test_check_rate_limit_keys_are_independent():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    # Agotar el límite para una IP no afecta a otra.
    for _ in range(3):
        await check_rate_limit(redis, "minerva:rl:test:1.1.1.1", max_requests=3, window=60)
    assert await check_rate_limit(redis, "minerva:rl:test:1.1.1.1", max_requests=3, window=60) is False
    assert await check_rate_limit(redis, "minerva:rl:test:9.9.9.9", max_requests=3, window=60) is True


def test_login_returns_429_after_exceeding_limit(client):
    """El 6to intento de login (default max=5) devuelve 429 con Retry-After."""
    client.post(
        "/auth/register",
        json={"email": "rl@iieg.gob.mx", "full_name": "RL User", "password": "testpass123"},
    )
    payload = {"email": "rl@iieg.gob.mx", "password": "testpass123"}

    for _ in range(5):
        assert client.post("/auth/login", json=payload).status_code == 200

    blocked = client.post("/auth/login", json=payload)
    assert blocked.status_code == 429
    assert "retry-after" in {k.lower() for k in blocked.headers}
