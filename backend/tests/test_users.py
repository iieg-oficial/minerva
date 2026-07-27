import pytest
from jose import jwt as jose_jwt
from sqlmodel import Session

import app.core.token_blacklist as token_blacklist
from app.core.dependencies.auth import _resolve_token
from app.core.token_blacklist import invalidate_user_tokens
from tests.conftest import test_engine


def test_list_users(client, admin_token):
    response = client.get("/users", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data


def test_get_user(client, admin_token, admin_user):
    user_id = admin_user["id"]
    response = client.get(f"/users/{user_id}", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 200
    assert response.json()["email"] == "testadmin@iieg.gob.mx"


def test_update_user_status(client, admin_token, admin_user):
    user_id = admin_user["id"]
    response = client.patch(
        f"/users/{user_id}/status",
        json={"status": "inactive"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "inactive"


def test_create_user_rechaza_password_vacio_o_corto(client, admin_token):
    """El alta exige una contraseña real: una vacía o menor a 8 caracteres se rechaza
    con 422 antes de llegar al servicio, para no dejar cuentas con contraseña débil."""
    admin_h = {"Authorization": f"Bearer {admin_token}"}
    for password in ("", "corta7"):
        resp = client.post(
            "/users",
            json={"email": f"weak-{len(password)}@iieg.gob.mx", "full_name": "Débil", "password": password},
            headers=admin_h,
        )
        assert resp.status_code == 422, f"contraseña {password!r} debería rechazarse: {resp.text}"


def test_update_user_rechaza_password_corto(client, admin_token, admin_user):
    """El mismo piso aplica al PATCH: cambiar la contraseña a una menor a 8 caracteres
    se rechaza con 422, para no debilitar una cuenta ya existente."""
    resp = client.patch(
        f"/users/{admin_user['id']}",
        json={"password": "corta7"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 422, resp.text


def _make_user_with_token(client, admin_token, email, make_session_token):
    """Crea un usuario y devuelve (user_id, su_token_de_sesión). Acuña el token
    directamente (el panel es cookie-only: /auth/login ya no devuelve el JWT)."""
    admin_h = {"Authorization": f"Bearer {admin_token}"}
    created = client.post(
        "/users",
        json={"email": email, "full_name": "Victima", "password": "pass123456"},
        headers=admin_h,
    )
    assert created.status_code == 201
    return created.json()["id"], make_session_token(email)


def test_password_change_invalidates_existing_tokens(client, admin_token, make_session_token):
    import time

    admin_h = {"Authorization": f"Bearer {admin_token}"}
    user_id, token = _make_user_with_token(client, admin_token, "victim-pass@iieg.gob.mx", make_session_token)
    user_h = {"Authorization": f"Bearer {token}"}
    assert client.get("/auth/me", headers=user_h).status_code == 200

    # `iat` es entero de segundos: aseguramos que el corte quede DESPUÉS del token.
    time.sleep(1)
    changed = client.patch(f"/users/{user_id}", json={"password": "otra123456"}, headers=admin_h)
    assert changed.status_code == 200

    # El token viejo deja de valer; el del admin (sin cambios) sigue.
    assert client.get("/auth/me", headers=user_h).status_code == 401
    assert client.get("/auth/me", headers=admin_h).status_code == 200


def test_deactivating_user_invalidates_existing_tokens(client, admin_token, make_session_token):
    import time

    admin_h = {"Authorization": f"Bearer {admin_token}"}
    user_id, token = _make_user_with_token(client, admin_token, "victim-status@iieg.gob.mx", make_session_token)
    user_h = {"Authorization": f"Bearer {token}"}
    assert client.get("/auth/me", headers=user_h).status_code == 200

    time.sleep(1)
    changed = client.patch(f"/users/{user_id}/status", json={"status": "inactive"}, headers=admin_h)
    assert changed.status_code == 200

    assert client.get("/auth/me", headers=user_h).status_code == 401


async def test_iat_before_cutoff_is_rejected(client, admin_token, make_session_token, fresh_redis, monkeypatch):
    user_id, token = _make_user_with_token(client, admin_token, "victim-before@iieg.gob.mx", make_session_token)
    iat = jose_jwt.get_unverified_claims(token)["iat"]
    monkeypatch.setattr(token_blacklist.time, "time", lambda: iat + 1)
    await invalidate_user_tokens(fresh_redis, user_id, ttl_seconds=3600)
    with Session(test_engine) as session:
        with pytest.raises(ValueError):
            await _resolve_token(token, session, fresh_redis, expected_types={"session"}, audience="minerva")


async def test_iat_equal_to_cutoff_is_rejected(client, admin_token, make_session_token, fresh_redis, monkeypatch):
    """Regresión: el corte usaba `<` y un token con iat == cutoff sobrevivía."""
    user_id, token = _make_user_with_token(client, admin_token, "victim-equal@iieg.gob.mx", make_session_token)
    iat = jose_jwt.get_unverified_claims(token)["iat"]
    monkeypatch.setattr(token_blacklist.time, "time", lambda: iat)
    await invalidate_user_tokens(fresh_redis, user_id, ttl_seconds=3600)
    with Session(test_engine) as session:
        with pytest.raises(ValueError):
            await _resolve_token(token, session, fresh_redis, expected_types={"session"}, audience="minerva")


async def test_iat_after_cutoff_is_accepted(client, admin_token, make_session_token, fresh_redis, monkeypatch):
    user_id, token = _make_user_with_token(client, admin_token, "victim-after@iieg.gob.mx", make_session_token)
    iat = jose_jwt.get_unverified_claims(token)["iat"]
    monkeypatch.setattr(token_blacklist.time, "time", lambda: iat - 1)
    await invalidate_user_tokens(fresh_redis, user_id, ttl_seconds=3600)
    with Session(test_engine) as session:
        payload = await _resolve_token(token, session, fresh_redis, expected_types={"session"}, audience="minerva")
    assert payload["sub"] == user_id
