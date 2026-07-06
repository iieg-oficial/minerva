"""Tests de clientes públicos (sin client_secret): PKCE obligatorio."""

import base64
import hashlib
import secrets

import pytest
from sqlmodel import Session

from app.core.exceptions import BadRequestError
from app.modules.applications.models import Application, RedirectURI
from app.modules.applications.schemas import ApplicationCreate
from app.modules.applications.service import ApplicationService
from app.modules.auth.service import AuthService
from app.modules.oidc.service import OIDCService
from app.modules.users.models import User
from tests.conftest import grant_role, test_engine

REDIRECT_URI = "https://publico.example.com/callback"
RFC_VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"


def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


@pytest.fixture
def public_ctx():
    with Session(test_engine) as session:
        app_row = Application(
            name="Cliente Público",
            slug="cliente-publico",
            client_secret_hash=None,
            status="active",
        )
        session.add(app_row)
        session.flush()
        session.add(RedirectURI(application_id=app_row.id, uri=REDIRECT_URI, environment="production"))
        user = User(email="publico@iieg.gob.mx", full_name="Cliente Público", auth_provider="local", status="active")
        session.add(user)
        grant_role(session, app_row.id, user.id)
        session.commit()
        session.refresh(app_row)
        session.refresh(user)
        OIDCService(session).ensure_active_signing_key()
        return {"client_id": app_row.client_id, "user_id": user.id}


def test_authorize_public_client_requires_code_challenge(public_ctx):
    with Session(test_engine) as session:
        svc = AuthService(session)
        with pytest.raises(BadRequestError):
            svc.authorize(public_ctx["client_id"], REDIRECT_URI, public_ctx["user_id"], "s", "openid")


def test_token_exchange_public_client_without_secret(client, public_ctx):
    verifier = secrets.token_urlsafe(32)
    with Session(test_engine) as session:
        url, _ = AuthService(session).authorize(
            public_ctx["client_id"],
            REDIRECT_URI,
            public_ctx["user_id"],
            "s",
            "openid",
            code_challenge=_challenge(verifier),
        )
    code = url.split("code=")[1].split("&")[0]

    resp = client.post(
        "/auth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": public_ctx["client_id"],
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["access_token"]


def test_token_exchange_public_client_requires_pkce_verifier(public_ctx):
    verifier = secrets.token_urlsafe(32)
    with Session(test_engine) as session:
        url, _ = AuthService(session).authorize(
            public_ctx["client_id"],
            REDIRECT_URI,
            public_ctx["user_id"],
            "s",
            "openid",
            code_challenge=_challenge(verifier),
        )
        code = url.split("code=")[1].split("&")[0]
        with pytest.raises(BadRequestError, match="code_verifier inválido"):
            AuthService(session).exchange_token(public_ctx["client_id"], code, REDIRECT_URI, code_verifier="otro")


def test_refresh_public_client_without_secret(client, public_ctx):
    verifier = secrets.token_urlsafe(32)
    with Session(test_engine) as session:
        url, _ = AuthService(session).authorize(
            public_ctx["client_id"],
            REDIRECT_URI,
            public_ctx["user_id"],
            "s",
            "openid",
            code_challenge=_challenge(verifier),
        )
    code = url.split("code=")[1].split("&")[0]
    tokens = client.post(
        "/auth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": public_ctx["client_id"],
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier,
        },
    ).json()

    resp = client.post(
        "/auth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": public_ctx["client_id"],
            "refresh_token": tokens["refresh_token"],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["access_token"]


def test_create_application_is_public_skips_secret():
    with Session(test_engine) as session:
        result = ApplicationService(session).create_application(
            ApplicationCreate(name="App Pública", slug="app-publica-test", is_public=True)
        )
    assert result.client_secret_hash is None


def test_create_application_default_still_generates_secret():
    with Session(test_engine) as session:
        result = ApplicationService(session).create_application(
            ApplicationCreate(name="App Confidencial", slug="app-confidencial-test")
        )
    assert result.client_secret_hash
