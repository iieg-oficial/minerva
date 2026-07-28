"""Contrato de error OAuth estándar (RFC 6749 §5.2) en `/auth/token` (issue #78).

Cada error mapeado trae `error` + `error_description` (además de `detail`, conservado por
compatibilidad) con status 400. Lo que NO está en el mapeo de 4 códigos (p. ej. una carrera de
rotación en curso) sigue respondiendo igual que antes, sin el campo `error`.
"""

import pytest
from sqlmodel import Session

from app.core.security import hash_secret
from app.modules.applications.models import Application, RedirectURI
from app.modules.auth.repository import RefreshTokenRepository, RefreshTokenRowLocked
from app.modules.auth.service import AuthService
from app.modules.oidc.service import OIDCService
from app.modules.users.models import User
from tests.conftest import grant_role, test_engine

CLIENT_SECRET = "secret-oauth-errors-test"
REDIRECT_URI = "https://cliente.example.com/callback"


@pytest.fixture
def app_ctx():
    with Session(test_engine) as session:
        app_row = Application(
            name="OAuth Errors App",
            slug="oauth-errors-app",
            client_secret_hash=hash_secret(CLIENT_SECRET),
            status="active",
        )
        session.add(app_row)
        session.flush()
        session.add(RedirectURI(application_id=app_row.id, uri=REDIRECT_URI, environment="production"))
        user = User(email="oautherrors@iieg.gob.mx", full_name="OAuth Errors User", status="active")
        session.add(user)
        grant_role(session, app_row.id, user.id)
        session.commit()
        session.refresh(app_row)
        session.refresh(user)
        OIDCService(session).ensure_active_signing_key()
        return {"client_id": app_row.client_id, "user_id": user.id}


def _mint_code(ctx: dict) -> str:
    with Session(test_engine) as session:
        url, _ = AuthService(session).authorize(ctx["client_id"], REDIRECT_URI, ctx["user_id"], "state-x", "openid")
    return url.split("code=")[1].split("&")[0]


def test_exchange_exitoso_no_trae_campo_error(client, app_ctx):
    code = _mint_code(app_ctx)
    resp = client.post(
        "/auth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": app_ctx["client_id"],
            "client_secret": CLIENT_SECRET,
            "code": code,
            "redirect_uri": REDIRECT_URI,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "error" not in body
    assert body["access_token"]


def test_grant_type_no_soportado_devuelve_error_oauth(client, app_ctx):
    code = _mint_code(app_ctx)
    resp = client.post(
        "/auth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": app_ctx["client_id"],
            "client_secret": CLIENT_SECRET,
            "code": code,
            "redirect_uri": REDIRECT_URI,
        },
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"] == "unsupported_grant_type"
    assert body["error_description"]
    assert body["detail"] == body["error_description"]


def test_parametros_faltantes_devuelve_invalid_request(client):
    resp = client.post("/auth/token", data={"grant_type": "authorization_code"})
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_request"


def test_client_secret_invalido_devuelve_invalid_client_sin_filtrar_el_secret(client, app_ctx):
    code = _mint_code(app_ctx)
    secreto_atacante = "secreto-adivinado-por-el-atacante"
    resp = client.post(
        "/auth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": app_ctx["client_id"],
            "client_secret": secreto_atacante,
            "code": code,
            "redirect_uri": REDIRECT_URI,
        },
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"] == "invalid_client"
    assert secreto_atacante not in resp.text
    assert CLIENT_SECRET not in resp.text


def test_code_ya_usado_devuelve_invalid_grant(client, app_ctx):
    code = _mint_code(app_ctx)
    data = {
        "grant_type": "authorization_code",
        "client_id": app_ctx["client_id"],
        "client_secret": CLIENT_SECRET,
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }
    first = client.post("/auth/token", data=data)
    assert first.status_code == 200

    reuse = client.post("/auth/token", data=data)
    assert reuse.status_code == 400
    assert reuse.json()["error"] == "invalid_grant"


def test_rotacion_en_curso_no_es_un_error_oauth_mapeado(client, app_ctx, monkeypatch):
    """Contención real (issue #38): otra rotación tiene el lock de fila ahora mismo. No es
    uno de los 4 códigos del issue #78, así que sigue respondiendo 409 sin campo `error`."""
    code = _mint_code(app_ctx)
    first = client.post(
        "/auth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": app_ctx["client_id"],
            "client_secret": CLIENT_SECRET,
            "code": code,
            "redirect_uri": REDIRECT_URI,
        },
    )
    refresh_token = first.json()["refresh_token"]

    def _locked(self, token_hash):
        raise RefreshTokenRowLocked()

    monkeypatch.setattr(RefreshTokenRepository, "get_by_hash_for_update", _locked)

    resp = client.post(
        "/auth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": app_ctx["client_id"],
            "client_secret": CLIENT_SECRET,
            "refresh_token": refresh_token,
        },
    )
    assert resp.status_code == 409
    assert "error" not in resp.json()
