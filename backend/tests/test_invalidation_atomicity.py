"""R11 (fail-closed): un fallo de escritura en Redis durante la invalidación de sesiones
no debe dejar PostgreSQL confirmado a medias.

Antes, `update_user` confirmaba el cambio de credenciales en PG y luego escribía el corte
de invalidación en Redis: si Redis fallaba después del commit, la contraseña ya había
cambiado pero las sesiones vigentes no quedaban invalidadas (fail-open al recuperarse Redis).
Ahora las invalidaciones van a Redis primero y PG se confirma después; si Redis falla, rollback.
"""

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_redis_write_failure_rolls_back_credential_change(client, admin_token, fresh_redis):
    client.post(
        "/auth/register",
        json={"email": "victima@iieg.gob.mx", "full_name": "Víctima", "password": "oldpass123"},
    )
    client.cookies.clear()
    items = client.get("/users?limit=500", headers=_auth(admin_token)).json()["items"]
    victim = next(u for u in items if u["email"] == "victima@iieg.gob.mx")

    # Redis cae justo en la escritura de la invalidación (el corte por `iat`).
    original_set = fresh_redis.set

    async def boom(*args, **kwargs):
        raise RedisConnectionError("redis down")

    fresh_redis.set = boom

    with pytest.raises(RedisConnectionError):
        client.patch(
            f"/users/{victim['id']}",
            json={"password": "newpass456"},
            headers=_auth(admin_token),
        )

    # Redis se recupera. Como hubo rollback, la contraseña NO cambió: la vieja sigue
    # sirviendo y la nueva no. (Si el commit de PG hubiera quedado, sería al revés → fail-open.)
    fresh_redis.set = original_set
    ok = client.post("/auth/login", json={"email": "victima@iieg.gob.mx", "password": "oldpass123"})
    assert ok.status_code == 200, "el cambio de contraseña no se revirtió: PG quedó confirmado a medias"
    client.cookies.clear()
    bad = client.post("/auth/login", json={"email": "victima@iieg.gob.mx", "password": "newpass456"})
    assert bad.status_code != 200
