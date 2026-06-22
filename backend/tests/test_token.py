"""Tests del token endpoint OIDC: form-encoded, id_token y access token RS256 (Fase 4)."""

import pytest
from sqlmodel import Session

from app.core.security import decode_token_rs256, hash_secret
from app.modules.applications.models import Application, RedirectURI
from app.modules.auth.service import AuthService
from app.modules.oidc.service import OIDCService
from app.modules.users.models import User
from tests.conftest import test_engine

CLIENT_SECRET = "secret-token-test"
REDIRECT_URI = "https://cliente.example.com/callback"


@pytest.fixture
def app_ctx():
    with Session(test_engine) as session:
        app_row = Application(
            name="Token App",
            slug="token-app",
            client_secret_hash=hash_secret(CLIENT_SECRET),
            status="active",
        )
        session.add(app_row)
        session.flush()
        session.add(RedirectURI(application_id=app_row.id, uri=REDIRECT_URI, environment="production"))
        user = User(email="token@iieg.gob.mx", full_name="Token User", auth_provider="local", status="active")
        session.add(user)
        session.commit()
        session.refresh(app_row)
        session.refresh(user)
        OIDCService(session).ensure_active_signing_key()
        return {"client_id": app_row.client_id, "user_id": user.id}


def _mint_code(ctx: dict, scope: str = "openid profile email", nonce: str | None = "n-123") -> str:
    with Session(test_engine) as session:
        url = AuthService(session).authorize(
            ctx["client_id"], REDIRECT_URI, ctx["user_id"], "state-x", scope, nonce=nonce
        )
    return url.split("code=")[1].split("&")[0]


def _jwks() -> dict:
    with Session(test_engine) as session:
        return OIDCService(session).build_jwks()


def test_token_form_encoded_returns_id_and_access_token(client, app_ctx):
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
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["id_token"]

    # id_token: aud = client_id, lleva el nonce capturado en /authorize.
    id_claims = decode_token_rs256(body["id_token"], _jwks(), audience=app_ctx["client_id"])
    assert id_claims["aud"] == app_ctx["client_id"]
    assert id_claims["nonce"] == "n-123"
    assert id_claims["email"] == "token@iieg.gob.mx"

    # access token: RS256 verificable por JWKS, aud = slug de la app, con jti.
    access_claims = decode_token_rs256(body["access_token"], _jwks())
    assert access_claims["aud"] == "token-app"
    assert "jti" in access_claims


def test_token_json_legacy_still_works(client, app_ctx):
    code = _mint_code(app_ctx)
    resp = client.post(
        "/auth/token",
        json={
            "client_id": app_ctx["client_id"],
            "client_secret": CLIENT_SECRET,
            "code": code,
            "redirect_uri": REDIRECT_URI,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["id_token"]


def test_token_without_openid_scope_omits_id_token(client, app_ctx):
    code = _mint_code(app_ctx, scope="profile email", nonce=None)
    resp = client.post(
        "/auth/token",
        data={
            "client_id": app_ctx["client_id"],
            "client_secret": CLIENT_SECRET,
            "code": code,
            "redirect_uri": REDIRECT_URI,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["id_token"] is None


def test_token_rejects_unsupported_grant_type(client, app_ctx):
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


def test_token_missing_params_rejected(client):
    resp = client.post("/auth/token", data={"grant_type": "authorization_code"})
    assert resp.status_code == 400
