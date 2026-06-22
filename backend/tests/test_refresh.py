"""Tests de refresh tokens: rotación, detección de reúso y revocación (Fase 4.5)."""

import fakeredis.aioredis
import pytest
from sqlmodel import Session

from app.core.security import decode_token_rs256, hash_secret
from app.core.token_blacklist import is_revoked, revoke_jti
from app.modules.applications.models import Application, RedirectURI
from app.modules.auth.service import AuthService
from app.modules.oidc.service import OIDCService
from app.modules.users.models import User
from tests.conftest import test_engine

CLIENT_SECRET = "secret-refresh-test"
REDIRECT_URI = "https://cliente.example.com/cb"


@pytest.fixture
def app_ctx():
    with Session(test_engine) as session:
        app_row = Application(
            name="Refresh App",
            slug="refresh-app",
            client_secret_hash=hash_secret(CLIENT_SECRET),
            status="active",
        )
        session.add(app_row)
        session.flush()
        session.add(RedirectURI(application_id=app_row.id, uri=REDIRECT_URI, environment="production"))
        user = User(email="refresh@iieg.gob.mx", full_name="Refresh User", auth_provider="local", status="active")
        session.add(user)
        session.commit()
        session.refresh(app_row)
        session.refresh(user)
        OIDCService(session).ensure_active_signing_key()
        return {"client_id": app_row.client_id, "user_id": user.id}


def _initial_tokens(client, ctx: dict) -> dict:
    """Recorre code -> token y devuelve el cuerpo (con refresh_token)."""
    with Session(test_engine) as session:
        url = AuthService(session).authorize(ctx["client_id"], REDIRECT_URI, ctx["user_id"], "s", "openid profile")
    code = url.split("code=")[1].split("&")[0]
    resp = client.post(
        "/auth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": ctx["client_id"],
            "client_secret": CLIENT_SECRET,
            "code": code,
            "redirect_uri": REDIRECT_URI,
        },
    )
    assert resp.status_code == 200
    return resp.json()


def _refresh(client, ctx: dict, refresh_token: str):
    return client.post(
        "/auth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": ctx["client_id"],
            "client_secret": CLIENT_SECRET,
            "refresh_token": refresh_token,
        },
    )


def test_exchange_issues_short_access_and_refresh(client, app_ctx):
    body = _initial_tokens(client, app_ctx)
    assert body["refresh_token"]
    assert body["expires_in"] == 15 * 60  # access token corto


def test_refresh_rotates_token(client, app_ctx):
    first = _initial_tokens(client, app_ctx)
    resp = _refresh(client, app_ctx, first["refresh_token"])
    assert resp.status_code == 200
    second = resp.json()
    assert second["refresh_token"] != first["refresh_token"]  # rotó
    assert second["access_token"]
    # el nuevo access token sigue siendo RS256 verificable por JWKS
    with Session(test_engine) as session:
        jwks = OIDCService(session).build_jwks()
    claims = decode_token_rs256(second["access_token"], jwks)
    assert claims["aud"] == "refresh-app"


def test_refresh_reuse_revokes_family(client, app_ctx):
    first = _initial_tokens(client, app_ctx)
    second = _refresh(client, app_ctx, first["refresh_token"]).json()

    # Reusar el primer refresh (ya rotado) → rechazo + revoca la familia.
    reuse = _refresh(client, app_ctx, first["refresh_token"])
    assert reuse.status_code == 400

    # El token rotado (second) también queda inservible por la revocación.
    after = _refresh(client, app_ctx, second["refresh_token"])
    assert after.status_code == 400


def test_revoke_endpoint_invalidates_refresh(client, app_ctx):
    body = _initial_tokens(client, app_ctx)
    revoke = client.post(
        "/auth/revoke",
        data={
            "client_id": app_ctx["client_id"],
            "client_secret": CLIENT_SECRET,
            "token": body["refresh_token"],
        },
    )
    assert revoke.status_code == 200
    assert _refresh(client, app_ctx, body["refresh_token"]).status_code == 400


def test_refresh_invalid_token_rejected(client, app_ctx):
    assert _refresh(client, app_ctx, "token-que-no-existe").status_code == 400


async def test_blacklist_helper_roundtrip():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    assert await is_revoked(redis, "jti-1") is False
    await revoke_jti(redis, "jti-1", 60)
    assert await is_revoked(redis, "jti-1") is True
    # jti vacío/None es no-op seguro.
    assert await is_revoked(redis, None) is False
