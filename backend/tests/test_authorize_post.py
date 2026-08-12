"""Tests de POST /auth/authorize (OIDC Core 3.1.2.1: el Authorization Endpoint debe
aceptar GET y POST form-urlencoded). El invariante es la equivalencia: el POST recorre
el mismo camino que el GET y llega al mismo destino."""

from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from sqlmodel import Session, select

from app.core.security import hash_secret
from app.modules.applications.models import Application, RedirectURI
from app.modules.oidc.service import OIDCService
from app.modules.users.models import User
from tests.conftest import grant_role, test_engine

CLIENT_SECRET = "post-authorize-secret"
REDIRECT_URI = "https://post.example.com/callback"


@pytest.fixture
def app_ctx(client):
    with Session(test_engine) as session:
        app_row = Application(
            name="Post App",
            slug="post-app",
            client_secret_hash=hash_secret(CLIENT_SECRET),
            status="active",
        )
        session.add(app_row)
        session.flush()
        session.add(RedirectURI(application_id=app_row.id, uri=REDIRECT_URI, environment="production"))
        user = User(
            email="post-authorize@iieg.gob.mx",
            full_name="Post User",
            status="active",
            last_login_at=datetime.now(timezone.utc),
        )
        session.add(user)
        grant_role(session, app_row.id, user.id)
        session.commit()
        session.refresh(app_row)
        session.refresh(user)
        OIDCService(session).ensure_active_signing_key()
        token = OIDCService(session).issue_session_token(user.id, user.email, user.full_name)
    return {"client_id": app_row.client_id, "token": token}


def _params(ctx: dict, **extra) -> dict:
    return {
        "client_id": ctx["client_id"],
        "redirect_uri": REDIRECT_URI,
        "state": "s",
        "scope": "openid",
        **extra,
    }


def _auth(ctx: dict) -> dict:
    return {"Authorization": f"Bearer {ctx['token']}"}


def _post(client, params: dict, headers: dict | None = None):
    return client.post("/auth/authorize", data=params, headers=headers or {}, follow_redirects=False)


def _get(client, params: dict, headers: dict | None = None):
    return client.get("/auth/authorize", params=params, headers=headers or {}, follow_redirects=False)


def test_post_and_get_reach_the_same_callback(client, app_ctx):
    """Mismos parámetros por GET y por POST → mismo destino (salvo el `code`, que es
    de un solo uso y se regenera en cada llamada)."""
    params = _params(app_ctx)
    get_resp = _get(client, params, _auth(app_ctx))
    post_resp = _post(client, params, _auth(app_ctx))

    assert get_resp.status_code in (302, 307)
    # 303 y no 307: el navegador debe seguir el callback con GET, no re-enviar el POST.
    assert post_resp.status_code == 303

    def target(location: str) -> str:
        return location.split("code=")[0]

    assert "code=" in post_resp.headers["location"]
    assert target(post_resp.headers["location"]) == target(get_resp.headers["location"])
    assert "state=s" in post_resp.headers["location"]


def test_post_preserves_state_byte_for_byte(client, app_ctx):
    """El `state` es la defensa anti-CSRF del consumidor: vuelve tal cual aunque traiga
    espacios, `&`, `=` o `#`."""
    state = "a b&c=d#e"
    resp = _post(client, _params(app_ctx, state=state), _auth(app_ctx))
    assert resp.status_code == 303
    assert parse_qs(urlparse(resp.headers["location"]).query)["state"] == [state]


def test_post_with_unregistered_redirect_uri_does_not_redirect(client, app_ctx):
    """El destino se valida ANTES de redirigir: nunca se manda al usuario a una URI
    no registrada (open redirect)."""
    resp = _post(
        client,
        _params(app_ctx, redirect_uri="https://atacante.example.com/cb"),
        _auth(app_ctx),
    )
    assert resp.status_code == 400
    assert "location" not in resp.headers


def test_post_unsupported_response_type_returns_error_to_client(client, app_ctx):
    resp = _post(client, _params(app_ctx, response_type="token"), _auth(app_ctx))
    assert resp.status_code == 303
    assert "error=unsupported_response_type" in resp.headers["location"]
    assert resp.headers["location"].startswith(REDIRECT_URI)


def test_post_without_session_carries_params_into_the_login_next(client, app_ctx):
    """Sin sesión el POST cae al login, y el `next=` tiene que llevar los parámetros:
    en un POST la query string está vacía, así que se reconstruyen desde el form."""
    resp = _post(client, _params(app_ctx))
    assert resp.status_code == 303
    location = resp.headers["location"]
    assert "/login?next=" in location
    assert "%2Fauthorize%3F" in location
    assert app_ctx["client_id"] in location  # los parámetros sobreviven al rebote


def test_post_prompt_none_without_session_returns_login_required(client, app_ctx):
    resp = _post(client, _params(app_ctx, prompt="none"))
    assert resp.status_code == 303
    assert "error=login_required" in resp.headers["location"]


def test_post_without_client_id_is_a_422_like_the_get(client, app_ctx):
    params = _params(app_ctx)
    del params["client_id"]
    assert _post(client, params, _auth(app_ctx)).status_code == 422
    assert _get(client, params, _auth(app_ctx)).status_code == 422


def test_post_with_the_panel_cookie_is_not_blocked_by_csrf(client, app_ctx):
    """El consumidor no puede conocer el token CSRF del panel: el POST del
    Authorization Endpoint está exento (ver `core/csrf.py`)."""
    client.post(
        "/auth/register",
        json={"email": "post-csrf@iieg.gob.mx", "full_name": "Usuario Prueba", "password": "testpass123"},
    )
    with Session(test_engine) as session:
        user = session.exec(select(User).where(User.email == "post-csrf@iieg.gob.mx")).first()
        assert user is not None
    # La cookie de panel quedó en el jar del TestClient; sin exención esto sería un 403.
    resp = _post(client, _params(app_ctx))
    assert resp.status_code == 303
