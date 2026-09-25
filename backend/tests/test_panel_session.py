"""Sesión del panel por cookie opaca + CSRF (patrón BFF, Issue #41).

Ejercita el camino REAL de producción: cookie `minerva_sid` (dev) → contenedor en
Redis → token `typ=session` validado por `_resolve_token`. No usa Bearer (a
diferencia de la suite legacy), así que el override de conftest cae al path de cookie.
"""

import asyncio

from app.core import panel_session
from app.core.config import settings
from app.core.security import create_access_token_rs256
from app.core.token_blacklist import is_revoked
from app.modules.oidc.service import OIDCService

COOKIE = settings.session_cookie_name


def _csrf_headers(csrf, origin=None):
    return {"X-CSRF-Token": csrf, "Origin": origin or settings.FRONTEND_URL}


def _register(client, email, password="testpass123"):
    full_name = f"Usuario {email.split('@')[0]}"
    return client.post("/auth/register", json={"email": email, "full_name": full_name, "password": password})


def _read_container(fake, sid):
    return asyncio.run(panel_session.read(fake, sid))


# 1. Login/register fija cookie HttpOnly (SameSite=Lax, Path=/) y NO devuelve el JWT.
def test_login_sets_httponly_cookie_without_jwt(client):
    resp = _register(client, "bff-1@iieg.gob.mx")
    assert resp.status_code == 201
    body = resp.json()
    assert "access_token" not in body and "token" not in str(body)
    assert body["csrf"] and body["active"]["email"] == "bff-1@iieg.gob.mx"
    set_cookie = resp.headers.get("set-cookie", "").lower()
    assert f"{COOKIE.lower()}=" in set_cookie
    assert "httponly" in set_cookie and "samesite=lax" in set_cookie and "path=/" in set_cookie


# 1b. En producción la cookie usa el prefijo __Host- y Secure (exige HTTPS); en dev,
#     nombre distinto sin Secure para no romper el desarrollo local HTTP.
def test_cookie_name_and_secure_by_environment(monkeypatch):
    monkeypatch.setattr(settings, "MINERVA_MODE", "production")
    assert settings.session_cookie_name == "__Host-minerva_sid"
    assert settings.session_cookie_secure is True
    monkeypatch.setattr(settings, "MINERVA_MODE", "dev")
    assert settings.session_cookie_name == "minerva_sid"
    assert settings.session_cookie_secure is False


# 2 + 3. Dos cuentas coexisten en un navegador y se puede cambiar la activa.
def test_two_accounts_coexist_and_switch(client):
    _register(client, "acc-a@iieg.gob.mx")
    _register(client, "acc-b@iieg.gob.mx")  # el jar reenvía la cookie → mismo contenedor
    view = client.get("/auth/session").json()
    subs = {a["email"]: a["sub"] for a in view["accounts"]}
    assert set(subs) == {"acc-a@iieg.gob.mx", "acc-b@iieg.gob.mx"}
    assert view["active"]["email"] == "acc-b@iieg.gob.mx"  # la última queda activa

    body = {"sub": subs["acc-a@iieg.gob.mx"]}
    r = client.post("/auth/session/active", json=body, headers=_csrf_headers(view["csrf"]))
    assert r.status_code == 200
    assert client.get("/auth/session").json()["active"]["email"] == "acc-a@iieg.gob.mx"


# 4. Una cuenta vencida se reporta como expired.
def test_expired_account_reported(client, fresh_redis):
    resp = _register(client, "exp@iieg.gob.mx")
    sid = resp.cookies.get(COOKIE)
    container = _read_container(fresh_redis, sid)
    for acc in container["accounts"].values():
        acc["exp"] = 1  # en el pasado
    asyncio.run(panel_session.write(fresh_redis, sid, container))
    view = client.get("/auth/session").json()
    assert view["accounts"][0]["expired"] is True


# 5. «Cerrar sesión» revoca la cuenta activa pero la deja en el selector, cerrada.
def test_logout_revokes_active_and_keeps_it_listed(client, fresh_redis):
    resp = _register(client, "soft@iieg.gob.mx")
    sid = resp.cookies.get(COOKIE)
    csrf = resp.json()["csrf"]
    jti = list(_read_container(fresh_redis, sid)["accounts"].values())[0]["jti"]

    assert client.post("/auth/logout", headers=_csrf_headers(csrf)).status_code == 200
    view = client.get("/auth/session").json()
    assert view["active"] is None and len(view["accounts"]) == 1
    account = view["accounts"][0]
    assert account["signed_out"] is True and account["expired"] is True
    assert asyncio.run(is_revoked(fresh_redis, jti)) is True
    assert all(a["token"] is None for a in _read_container(fresh_redis, sid)["accounts"].values())
    assert client.get("/auth/me").status_code == 401  # sin activa


# 5b. Una cuenta cerrada no se reactiva desde el selector sin contraseña (409); con
#     `/auth/login` vuelve a entrar.
def test_signed_out_account_requires_password(client):
    resp = _register(client, "closed@iieg.gob.mx")
    csrf = resp.json()["csrf"]
    sub = resp.json()["active"]["sub"]
    assert client.post("/auth/logout", headers=_csrf_headers(csrf)).status_code == 200

    csrf = client.get("/auth/session").json()["csrf"]
    r = client.post("/auth/session/active", json={"sub": sub}, headers=_csrf_headers(csrf))
    assert r.status_code == 409
    assert client.get("/auth/me").status_code == 401

    relogin = client.post("/auth/login", json={"email": "closed@iieg.gob.mx", "password": "testpass123"})
    assert relogin.status_code == 200
    assert client.get("/auth/me").status_code == 200


# 5c. Multi-cuenta: cerrar la activa no toca a las demás, que siguen activables sin
#     contraseña mientras su sesión esté viva.
def test_logout_keeps_other_live_accounts_switchable(client, fresh_redis):
    _register(client, "keep-a@iieg.gob.mx")
    resp_b = _register(client, "keep-b@iieg.gob.mx")  # queda activa
    sid = resp_b.cookies.get(COOKIE)
    view = client.get("/auth/session").json()
    subs = {a["email"]: a["sub"] for a in view["accounts"]}
    jti_a = _read_container(fresh_redis, sid)["accounts"][subs["keep-a@iieg.gob.mx"]]["jti"]

    assert client.post("/auth/logout", headers=_csrf_headers(view["csrf"])).status_code == 200
    assert asyncio.run(is_revoked(fresh_redis, jti_a)) is False

    csrf = client.get("/auth/session").json()["csrf"]
    body = {"sub": subs["keep-a@iieg.gob.mx"]}
    assert client.post("/auth/session/active", json=body, headers=_csrf_headers(csrf)).status_code == 200
    assert client.get("/auth/me").json()["user"]["email"] == "keep-a@iieg.gob.mx"


# 5d. Si el token guardado ya no vale (revocado por otra vía), el selector tampoco lo
#     reactiva: responde 409 y la cuenta pasa a mostrarse cerrada.
def test_set_active_rejects_revoked_token(client, fresh_redis):
    from app.core.token_blacklist import revoke_jti

    _register(client, "rev-a@iieg.gob.mx")
    resp_b = _register(client, "rev-b@iieg.gob.mx")
    sid = resp_b.cookies.get(COOKIE)
    view = client.get("/auth/session").json()
    sub_a = next(a["sub"] for a in view["accounts"] if a["email"] == "rev-a@iieg.gob.mx")
    asyncio.run(revoke_jti(fresh_redis, _read_container(fresh_redis, sid)["accounts"][sub_a]["jti"], 60))

    r = client.post("/auth/session/active", json={"sub": sub_a}, headers=_csrf_headers(view["csrf"]))
    assert r.status_code == 409
    closed = next(a for a in client.get("/auth/session").json()["accounts"] if a["sub"] == sub_a)
    assert closed["signed_out"] is True
    assert client.get("/auth/me").json()["user"]["email"] == "rev-b@iieg.gob.mx"  # la activa sigue


# 6. Quitar una cuenta la revoca sin tocar las demás.
def test_remove_account_revokes_only_that_one(client, fresh_redis):
    _register(client, "rm-a@iieg.gob.mx")
    resp_b = _register(client, "rm-b@iieg.gob.mx")
    sid = resp_b.cookies.get(COOKIE)
    view = client.get("/auth/session").json()
    subs = {a["email"]: a["sub"] for a in view["accounts"]}
    container = _read_container(fresh_redis, sid)
    jti_a = container["accounts"][subs["rm-a@iieg.gob.mx"]]["jti"]
    jti_b = container["accounts"][subs["rm-b@iieg.gob.mx"]]["jti"]

    r = client.delete(f"/auth/session/accounts/{subs['rm-a@iieg.gob.mx']}", headers=_csrf_headers(view["csrf"]))
    assert r.status_code == 200 and r.json()["removed"] is True
    assert asyncio.run(is_revoked(fresh_redis, jti_a)) is True
    assert asyncio.run(is_revoked(fresh_redis, jti_b)) is False
    remaining = [a["email"] for a in client.get("/auth/session").json()["accounts"]]
    assert remaining == ["rm-b@iieg.gob.mx"]


# 7. Logout-all revoca todas + destruye el contenedor + borra cookie.
def test_logout_all_destroys_session(client, fresh_redis):
    _register(client, "all-a@iieg.gob.mx")
    resp_b = _register(client, "all-b@iieg.gob.mx")
    sid = resp_b.cookies.get(COOKIE)
    csrf = client.get("/auth/session").json()["csrf"]
    jtis = [a["jti"] for a in _read_container(fresh_redis, sid)["accounts"].values()]

    r = client.post("/auth/logout-all", headers=_csrf_headers(csrf))
    assert r.status_code == 200
    assert all(asyncio.run(is_revoked(fresh_redis, j)) for j in jtis)
    assert _read_container(fresh_redis, sid) is None  # contenedor destruido
    assert "Max-Age=0" in r.headers.get("set-cookie", "") or "expires" in r.headers.get("set-cookie", "").lower()


# 8. SID inexistente/manipulado → 401.
def test_tampered_sid_rejected(client):
    client.cookies.clear()
    assert client.get("/auth/me", cookies={COOKIE: "sid-que-no-existe"}).status_code == 401
    assert client.get("/auth/me", cookies={COOKIE: "otro-sid-falso"}).status_code == 401


# 9. La rotación de sid (en refresh) invalida el sid anterior.
def test_sid_rotation_invalidates_old(client):
    resp = _register(client, "rot@iieg.gob.mx")
    old_sid = resp.cookies.get(COOKIE)
    csrf = resp.json()["csrf"]
    r = client.post("/auth/refresh", headers=_csrf_headers(csrf))
    assert r.status_code == 200
    new_sid = r.cookies.get(COOKIE)
    assert new_sid and new_sid != old_sid
    client.cookies.clear()
    assert client.get("/auth/me", cookies={COOKIE: old_sid}).status_code == 401  # sid viejo muerto


# 10. Mutación sin CSRF o con CSRF incorrecto → 403.
def test_csrf_required_for_mutations(client):
    _register(client, "csrf@iieg.gob.mx")
    assert client.post("/auth/logout").status_code == 403  # sin token
    assert client.post("/auth/logout", headers=_csrf_headers("token-incorrecto")).status_code == 403


# 11. Origin no permitido → 403.
def test_bad_origin_rejected(client):
    resp = _register(client, "origin@iieg.gob.mx")
    csrf = resp.json()["csrf"]
    r = client.post("/auth/logout", headers=_csrf_headers(csrf, origin="https://evil.example"))
    assert r.status_code == 403


# 12. Un access token de consumidor (typ=access) no vale como sesión del panel,
#     aunque su firma sea válida: el path del panel exige typ=session.
def test_consumer_access_token_not_valid_as_panel(client, fresh_redis):
    from sqlmodel import Session

    from tests.conftest import test_engine

    with Session(test_engine) as s:
        kid, pem = OIDCService(s).get_active_private_pem()
    access = create_access_token_rs256("user-x", "u@x", "U", kid, pem, application_slug="portal_demo", typ="access")

    sid = panel_session.new_sid()
    container = panel_session.empty_container()
    panel_session.add_account(container, "user-x", access, email="u@x", name="U", is_admin=False, exp=0, jti="j")
    asyncio.run(panel_session.write(fresh_redis, sid, container))

    client.cookies.clear()
    assert client.get("/auth/me", cookies={COOKIE: sid}).status_code == 401


# 13/15. /authorize reconoce la cookie de sesión del panel y la cuenta activa.
def test_authorize_uses_panel_cookie(client):
    from sqlmodel import Session, select

    from app.core.security import hash_secret
    from app.modules.applications.models import Application, RedirectURI
    from app.modules.users.models import User
    from tests.conftest import grant_role, test_engine

    _register(client, "authz@iieg.gob.mx")  # deja la cookie de sesión en el jar
    redirect_uri = "https://cons.example.com/cb"
    with Session(test_engine) as s:
        app_row = Application(name="Cons", slug="cons", status="active", client_secret_hash=hash_secret("x"))
        s.add(app_row)
        s.flush()
        s.add(RedirectURI(application_id=app_row.id, uri=redirect_uri, environment="production"))
        user = s.exec(select(User).where(User.email == "authz@iieg.gob.mx")).first()
        grant_role(s, app_row.id, user.id)
        s.commit()
        s.refresh(app_row)
        client_id = app_row.client_id

    resp = client.get(
        "/auth/authorize",
        params={"client_id": client_id, "redirect_uri": redirect_uri, "state": "s", "scope": "openid"},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307)
    location = resp.headers["location"]
    assert location.startswith(redirect_uri) and "code=" in location
