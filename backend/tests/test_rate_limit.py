"""Tests del rate limiting con Redis (ventana deslizante)."""

import time

import fakeredis.aioredis
import pytest
from sqlmodel import Session, select

from app.core.config import settings
from app.core.exceptions import TooManyRequestsError
from app.core.rate_limit import check_rate_limit, clear_failures, enforce_failure_limit, record_failure
from app.modules.audit.models import AuditLog
from tests.conftest import test_engine


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


def _login(client, email, password):
    return client.post("/auth/login", json={"email": email, "password": password})


def _register(client, email):
    client.post("/auth/register", json={"email": email, "full_name": "RL User", "password": "testpass123"})


def test_login_account_blocked_after_max_failures(client):
    """Tras RATE_LIMIT_LOGIN_MAX (5) fallos de una cuenta, esa cuenta responde 429 con
    Retry-After aunque la contraseña sea correcta, y queda registro en la auditoría."""
    _register(client, "rl@iieg.gob.mx")

    for _ in range(5):
        assert _login(client, "rl@iieg.gob.mx", "incorrecta").status_code == 400

    blocked = _login(client, "rl@iieg.gob.mx", "testpass123")
    assert blocked.status_code == 429
    assert 0 < int(blocked.headers["retry-after"]) <= 900

    with Session(test_engine) as session:
        logs = session.exec(select(AuditLog).where(AuditLog.action == "rate_limit_exceeded")).all()
    assert len(logs) == 1
    assert logs[0].event_metadata == {"endpoint": "login_account", "email": "rl@iieg.gob.mx"}


def test_login_account_limit_normalizes_email(client):
    """El contador es por correo normalizado: variar mayúsculas o espacios no lo reinicia."""
    _register(client, "norm@iieg.gob.mx")
    for email in ("norm@iieg.gob.mx", "NORM@iieg.gob.mx", " Norm@IIEG.gob.mx ", "norm@iieg.gob.mx", "nOrm@iieg.gob.mx"):
        _login(client, email, "incorrecta")
    assert _login(client, "norm@iieg.gob.mx", "testpass123").status_code == 429


def test_login_account_limit_same_response_for_unknown_account(client):
    """Una cuenta inexistente se bloquea igual y con la misma respuesta que una real: el
    límite no revela qué correos existen."""
    _register(client, "real@iieg.gob.mx")
    for _ in range(5):
        _login(client, "real@iieg.gob.mx", "incorrecta")
        _login(client, "fantasma@iieg.gob.mx", "incorrecta")

    real = _login(client, "real@iieg.gob.mx", "incorrecta")
    ghost = _login(client, "fantasma@iieg.gob.mx", "incorrecta")
    assert real.status_code == ghost.status_code == 429
    assert real.json() == ghost.json()


def test_login_success_clears_account_counter(client):
    """Un login exitoso limpia los fallos acumulados de la cuenta."""
    _register(client, "clear@iieg.gob.mx")
    for _ in range(4):
        _login(client, "clear@iieg.gob.mx", "incorrecta")
    assert _login(client, "clear@iieg.gob.mx", "testpass123").status_code == 200

    for _ in range(4):
        assert _login(client, "clear@iieg.gob.mx", "incorrecta").status_code == 400
    assert _login(client, "clear@iieg.gob.mx", "testpass123").status_code == 200


def test_login_account_limit_is_per_account(client):
    """Bloquear una cuenta no afecta a otra que entra desde la misma IP (el caso del WAF)."""
    _register(client, "victima@iieg.gob.mx")
    _register(client, "colega@iieg.gob.mx")
    for _ in range(5):
        _login(client, "victima@iieg.gob.mx", "incorrecta")
    assert _login(client, "victima@iieg.gob.mx", "testpass123").status_code == 429
    assert _login(client, "colega@iieg.gob.mx", "testpass123").status_code == 200


def test_login_successes_do_not_consume_account_limit(client):
    """Los ingresos correctos no cuentan: el límite por cuenta es de fallos."""
    _register(client, "ok@iieg.gob.mx")
    for _ in range(8):
        assert _login(client, "ok@iieg.gob.mx", "testpass123").status_code == 200


def test_login_ip_limit_still_applies(client, monkeypatch):
    """El límite por IP sigue como segundo nivel, con su propio umbral, y corta aunque cada
    intento sea contra una cuenta distinta (password spraying)."""
    monkeypatch.setattr(settings, "RATE_LIMIT_LOGIN_IP_MAX", 3)
    for i in range(3):
        assert _login(client, f"spray{i}@iieg.gob.mx", "incorrecta").status_code == 400
    blocked = _login(client, "spray9@iieg.gob.mx", "incorrecta")
    assert blocked.status_code == 429
    assert "retry-after" in {k.lower() for k in blocked.headers}

    with Session(test_engine) as session:
        logs = session.exec(select(AuditLog).where(AuditLog.action == "rate_limit_exceeded")).all()
    assert [log.event_metadata for log in logs] == [{"endpoint": "login"}]


async def test_failure_limit_retry_after_tracks_oldest_failure():
    """Retry-After es lo que falta para que expire el fallo más viejo, no la ventana entera."""
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    key = "minerva:rl:test:cuenta"
    now = time.time()
    await redis.zadd(key, {"viejo": now - 50, "nuevo": now - 10})

    with pytest.raises(TooManyRequestsError) as exc:
        await enforce_failure_limit(redis, key, max_failures=2, window=60)
    assert 1 <= int(exc.value.headers["Retry-After"]) <= 11

    await clear_failures(redis, key)
    await enforce_failure_limit(redis, key, max_failures=2, window=60)
    await record_failure(redis, key, window=60)
    assert await redis.zcard(key) == 1
