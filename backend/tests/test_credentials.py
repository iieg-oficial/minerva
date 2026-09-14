"""Ciclo de vida de la credencial: invitación, restablecimiento, cambio obligatorio y cambio propio.

Varios tests esperan 1 s antes de iniciar sesión tras fijar la contraseña: el corte de
invalidación por `iat` es de segundos y rechaza también los tokens emitidos en el mismo
segundo que el corte (ver `test_users.py`).
"""

import time
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from app.core.config import settings
from app.modules.credentials.models import CredentialToken
from tests.conftest import test_engine

NEW_PASSWORD = "nueva-clave-123"


def _admin(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


def _token_from(url: str) -> str:
    return url.split("#token=", 1)[1]


def _create_pending(client, admin_token, email="invitada@iieg.gob.mx"):
    resp = client.post("/users", json={"email": email, "full_name": "Persona Invitada"}, headers=_admin(admin_token))
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_active(client, admin_token, email="activa@iieg.gob.mx", password="pass123456"):
    resp = client.post(
        "/users",
        json={"email": email, "full_name": "Persona Activa", "password": password},
        headers=_admin(admin_token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _set_password(client, token, password=NEW_PASSWORD):
    return client.post("/auth/credential", json={"token": token, "password": password})


def _login(client, email, password):
    resp = client.post("/auth/login", json={"email": email, "password": password})
    # Sin la cookie en el jar, las llamadas Bearer siguientes del admin no pasan por CSRF.
    client.cookies.clear()
    return resp


def _register_with_session(client, email, password="testpass123"):
    resp = client.post("/auth/register", json={"email": email, "full_name": "Usuario Propio", "password": password})
    assert resp.status_code == 201, resp.text
    return {"X-CSRF-Token": resp.json()["csrf"], "Origin": settings.FRONTEND_URL}


# --- Alta sin credencial (invitación) -----------------------------------------


def test_create_without_password_leaves_user_pending_with_invitation(client, admin_token):
    body = _create_pending(client, admin_token)
    assert body["status"] == "pending"
    assert body["credential_link"]["purpose"] == "invite"
    assert body["credential_link"]["url"].startswith(f"{settings.FRONTEND_URL}/activar#token=")
    assert _login(client, "invitada@iieg.gob.mx", "cualquiera123").status_code == 400


def test_create_with_password_has_no_invitation(client, admin_token):
    body = _create_active(client, admin_token)
    assert body["status"] == "active"
    assert body["credential_link"] is None


def test_invitation_sets_password_and_activates_user(client, admin_token):
    token = _token_from(_create_pending(client, admin_token)["credential_link"]["url"])

    inspected = client.post("/auth/credential/inspect", json={"token": token})
    assert inspected.status_code == 200
    assert inspected.json()["purpose"] == "invite"
    assert inspected.json()["email"] == "i***@iieg.gob.mx"

    assert _set_password(client, token).status_code == 200
    time.sleep(1)
    assert _login(client, "invitada@iieg.gob.mx", NEW_PASSWORD).status_code == 200


def test_credential_link_is_single_use(client, admin_token):
    token = _token_from(_create_pending(client, admin_token)["credential_link"]["url"])
    assert _set_password(client, token).status_code == 200
    assert _set_password(client, token, "otra-clave-456").status_code == 400
    assert client.post("/auth/credential/inspect", json={"token": token}).status_code == 400


def test_expired_link_is_rejected(client, admin_token):
    token = _token_from(_create_pending(client, admin_token)["credential_link"]["url"])
    with Session(test_engine) as session:
        row = session.exec(select(CredentialToken)).one()
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        session.add(row)
        session.commit()
    assert _set_password(client, token).status_code == 400


def test_unknown_token_is_rejected(client):
    assert _set_password(client, "no-existe").status_code == 400


def test_new_link_invalidates_the_previous_one(client, admin_token):
    user = _create_pending(client, admin_token)
    old_token = _token_from(user["credential_link"]["url"])

    resp = client.post(f"/users/{user['id']}/credential-link", headers=_admin(admin_token))
    assert resp.status_code == 201
    assert resp.json()["purpose"] == "invite"

    assert _set_password(client, old_token).status_code == 400
    assert _set_password(client, _token_from(resp.json()["url"])).status_code == 200


# --- Restablecimiento por administrador ----------------------------------------


def test_reset_link_for_active_user_replaces_password(client, admin_token):
    user = _create_active(client, admin_token)
    resp = client.post(f"/users/{user['id']}/credential-link", headers=_admin(admin_token))
    assert resp.status_code == 201
    assert resp.json()["purpose"] == "reset"

    assert _set_password(client, _token_from(resp.json()["url"])).status_code == 200
    time.sleep(1)
    assert _login(client, "activa@iieg.gob.mx", "pass123456").status_code == 400
    assert _login(client, "activa@iieg.gob.mx", NEW_PASSWORD).status_code == 200


def test_credential_link_requires_admin(client, non_admin_token, admin_token):
    user = _create_active(client, admin_token)
    resp = client.post(f"/users/{user['id']}/credential-link", headers={"Authorization": f"Bearer {non_admin_token}"})
    assert resp.status_code == 403


# --- Cambio obligatorio ---------------------------------------------------------


def test_admin_password_reset_forces_change_on_next_login(client, admin_token):
    user = _create_active(client, admin_token)
    patched = client.patch(f"/users/{user['id']}", json={"password": "temporal123"}, headers=_admin(admin_token))
    assert patched.status_code == 200
    assert patched.json()["password_change_required"] is True

    time.sleep(1)
    resp = _login(client, "activa@iieg.gob.mx", "temporal123")
    assert resp.status_code == 403
    assert resp.json()["code"] == "password_change_required"
    assert resp.headers.get("set-cookie") is None

    assert _set_password(client, resp.json()["credential_token"]).status_code == 200
    time.sleep(1)
    assert _login(client, "activa@iieg.gob.mx", NEW_PASSWORD).status_code == 200


def test_admin_password_reset_can_skip_forced_change(client, admin_token):
    user = _create_active(client, admin_token)
    patched = client.patch(
        f"/users/{user['id']}",
        json={"password": "temporal123", "require_change": False},
        headers=_admin(admin_token),
    )
    assert patched.status_code == 200
    time.sleep(1)
    assert _login(client, "activa@iieg.gob.mx", "temporal123").status_code == 200


# --- Cambio propio --------------------------------------------------------------


def test_self_password_change_logs_the_account_out(client):
    headers = _register_with_session(client, "propia@iieg.gob.mx")
    resp = client.post(
        "/auth/password", json={"current_password": "testpass123", "new_password": NEW_PASSWORD}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert client.get("/auth/me").status_code == 401

    time.sleep(1)
    assert _login(client, "propia@iieg.gob.mx", "testpass123").status_code == 400
    assert _login(client, "propia@iieg.gob.mx", NEW_PASSWORD).status_code == 200


def test_self_password_change_rejects_wrong_current_password(client):
    headers = _register_with_session(client, "propia-mal@iieg.gob.mx")
    resp = client.post(
        "/auth/password", json={"current_password": "equivocada1", "new_password": NEW_PASSWORD}, headers=headers
    )
    assert resp.status_code == 400
    assert client.get("/auth/me").status_code == 200


def test_self_password_change_requires_csrf(client):
    _register_with_session(client, "propia-csrf@iieg.gob.mx")
    resp = client.post("/auth/password", json={"current_password": "testpass123", "new_password": NEW_PASSWORD})
    assert resp.status_code == 403


# --- Protecciones del endpoint público ------------------------------------------


def test_credential_endpoint_is_csrf_exempt_with_panel_cookie(client):
    _register_with_session(client, "con-cookie@iieg.gob.mx")
    assert _set_password(client, "no-existe").status_code == 400


def test_credential_endpoints_are_rate_limited(client, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_CREDENTIAL_MAX", 2)
    for _ in range(2):
        assert client.post("/auth/credential/inspect", json={"token": "no-existe"}).status_code == 400
    assert client.post("/auth/credential/inspect", json={"token": "no-existe"}).status_code == 429


# --- Enlaces que no deben sobrevivir --------------------------------------------


def test_suspending_user_voids_pending_link(client, admin_token):
    user = _create_active(client, admin_token)
    link = client.post(f"/users/{user['id']}/credential-link", headers=_admin(admin_token)).json()
    suspended = client.patch(f"/users/{user['id']}/status", json={"status": "suspended"}, headers=_admin(admin_token))
    assert suspended.status_code == 200
    assert _set_password(client, _token_from(link["url"])).status_code == 400


def test_no_link_for_suspended_user(client, admin_token):
    user = _create_active(client, admin_token)
    client.patch(f"/users/{user['id']}/status", json={"status": "suspended"}, headers=_admin(admin_token))
    resp = client.post(f"/users/{user['id']}/credential-link", headers=_admin(admin_token))
    assert resp.status_code == 400


def test_self_password_change_voids_pending_link(client, admin_token):
    headers = _register_with_session(client, "propia-enlace@iieg.gob.mx")
    sub = client.get("/auth/session").json()["active"]["sub"]
    # La cookie del usuario sigue en el jar: el admin pasa el CSRF de ese contenedor.
    link = client.post(f"/users/{sub}/credential-link", headers={**headers, **_admin(admin_token)})
    assert link.status_code == 201

    changed = client.post(
        "/auth/password", json={"current_password": "testpass123", "new_password": NEW_PASSWORD}, headers=headers
    )
    assert changed.status_code == 200
    assert _set_password(client, _token_from(link.json()["url"]), "otra-clave-456").status_code == 400


def test_pending_status_cannot_be_set_by_hand(client, admin_token):
    user = _create_active(client, admin_token)
    resp = client.patch(f"/users/{user['id']}/status", json={"status": "pending"}, headers=_admin(admin_token))
    assert resp.status_code == 400


def test_admin_password_on_pending_user_activates_it_and_voids_invitation(client, admin_token):
    user = _create_pending(client, admin_token)
    patched = client.patch(f"/users/{user['id']}", json={"password": "temporal123"}, headers=_admin(admin_token))
    assert patched.status_code == 200
    assert patched.json()["status"] == "active"
    assert _set_password(client, _token_from(user["credential_link"]["url"])).status_code == 400
