"""Tests de Modo B: GET /authorize sin Bearer (sistema externo con redirect de
navegador crudo, sin sesión previa en Minerva)."""

import pytest
from sqlmodel import Session

from app.core.security import hash_secret
from app.modules.applications.models import Application, RedirectURI
from app.modules.oidc.service import OIDCService
from tests.conftest import test_engine

CLIENT_SECRET = "modeb-secret"
REDIRECT_URI = "https://externo.example.com/callback"


@pytest.fixture
def app_ctx():
    with Session(test_engine) as session:
        app_row = Application(
            name="Externo",
            slug="externo",
            client_secret_hash=hash_secret(CLIENT_SECRET),
            status="active",
        )
        session.add(app_row)
        session.flush()
        session.add(RedirectURI(application_id=app_row.id, uri=REDIRECT_URI, environment="production"))
        session.commit()
        session.refresh(app_row)
        OIDCService(session).ensure_active_signing_key()
        return {"client_id": app_row.client_id}


def test_authorize_without_bearer_redirects_to_frontend_login(client, app_ctx):
    resp = client.get(
        "/auth/authorize",
        params={
            "client_id": app_ctx["client_id"],
            "redirect_uri": REDIRECT_URI,
            "state": "s",
            "scope": "openid",
        },
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307)
    location = resp.headers["location"]
    assert "/login?next=" in location
    assert "%2Fauthorize%3F" in location  # next= apunta a /authorize?... codificado


def test_authorize_without_bearer_invalid_client_returns_400_not_redirect(client):
    """Sin sesión Y con client_id inexistente: no debe redirigir (open redirect),
    debe rechazar con 400 antes de decidir a dónde mandar al usuario."""
    resp = client.get(
        "/auth/authorize",
        params={
            "client_id": "no-existe",
            "redirect_uri": "https://atacante.example.com/cb",
            "state": "s",
            "scope": "openid",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 400


def test_authorize_url_unaffected_still_requires_bearer(client, app_ctx):
    """`/authorize/url` (Modo A, consumido por la SPA) sigue exigiendo Bearer."""
    resp = client.get(
        "/auth/authorize/url",
        params={
            "client_id": app_ctx["client_id"],
            "redirect_uri": REDIRECT_URI,
            "state": "s",
            "scope": "openid",
        },
    )
    assert resp.status_code == 401
