"""Tests de GET /userinfo (OIDC Core 5.3): claims filtrados por scope."""

import pytest
from sqlmodel import Session

from app.core.security import hash_secret
from app.modules.applications.models import Application, RedirectURI
from app.modules.auth.service import AuthService
from app.modules.oidc.service import OIDCService
from app.modules.users.models import User
from tests.conftest import grant_role, test_engine

CLIENT_SECRET = "userinfo-secret"
REDIRECT_URI = "https://cliente.example.com/callback"


@pytest.fixture
def app_ctx():
    with Session(test_engine) as session:
        app_row = Application(
            name="UserInfo App",
            slug="userinfo-app",
            client_secret_hash=hash_secret(CLIENT_SECRET),
            status="active",
        )
        session.add(app_row)
        session.flush()
        session.add(RedirectURI(application_id=app_row.id, uri=REDIRECT_URI, environment="production"))
        user = User(email="userinfo@iieg.gob.mx", full_name="UserInfo User", status="active")
        session.add(user)
        grant_role(session, app_row.id, user.id)
        session.commit()
        session.refresh(app_row)
        session.refresh(user)
        OIDCService(session).ensure_active_signing_key()
        return {"client_id": app_row.client_id, "user_id": user.id}


def _access_token(client, ctx: dict, scope: str) -> str:
    with Session(test_engine) as session:
        url, _ = AuthService(session).authorize(ctx["client_id"], REDIRECT_URI, ctx["user_id"], "s", scope)
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
    return resp.json()["access_token"]


def test_userinfo_openid_only_returns_just_sub(client, app_ctx):
    token = _access_token(client, app_ctx, "openid")
    resp = client.get("/userinfo", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"sub": app_ctx["user_id"]}


def test_userinfo_filters_profile_and_email_claims(client, app_ctx):
    token = _access_token(client, app_ctx, "openid profile email")
    resp = client.get("/userinfo", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["sub"] == app_ctx["user_id"]
    assert body["name"] == "UserInfo User"
    assert body["preferred_username"] == "userinfo@iieg.gob.mx"
    assert body["email"] == "userinfo@iieg.gob.mx"
    assert body["email_verified"] is False


def test_userinfo_requires_bearer(client):
    resp = client.get("/userinfo")
    assert resp.status_code == 401


def test_userinfo_rejects_revoked_token(client, app_ctx, fresh_redis):
    import asyncio

    from jose import jwt as jose_jwt

    from app.core.token_blacklist import revoke_jti

    token = _access_token(client, app_ctx, "openid")
    resp = client.get("/userinfo", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200

    jti = jose_jwt.get_unverified_claims(token)["jti"]
    asyncio.run(revoke_jti(fresh_redis, jti, 60))

    resp = client.get("/userinfo", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
