"""Tests de `prompt` y `max_age` en /authorize (OIDC Core 3.1.2.1)."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session

from app.core.security import hash_secret
from app.modules.applications.models import Application, RedirectURI
from app.modules.oidc.service import OIDCService
from app.modules.users.models import User
from tests.conftest import test_engine

CLIENT_SECRET = "prompt-secret"
REDIRECT_URI = "https://prompt.example.com/callback"


@pytest.fixture
def app_ctx():
    with Session(test_engine) as session:
        app_row = Application(
            name="Prompt App",
            slug="prompt-app",
            client_secret_hash=hash_secret(CLIENT_SECRET),
            status="active",
        )
        session.add(app_row)
        session.flush()
        session.add(RedirectURI(application_id=app_row.id, uri=REDIRECT_URI, environment="production"))
        user = User(
            email="prompt@iieg.gob.mx",
            full_name="Prompt User",
            auth_provider="local",
            status="active",
            last_login_at=datetime.now(timezone.utc),
        )
        session.add(user)
        session.commit()
        session.refresh(app_row)
        session.refresh(user)
        OIDCService(session).ensure_active_signing_key()
        return {"client_id": app_row.client_id, "user_id": user.id}


def _login_and_get_token(client, email: str, password: str = "testpass123") -> str:
    resp = client.post("/auth/register", json={"email": email, "full_name": "U", "password": password})
    return resp.json()["access_token"]


def test_prompt_login_forces_redirect_to_login(client, app_ctx):
    token = _login_and_get_token(client, "prompt-login@iieg.gob.mx")
    resp = client.get(
        "/auth/authorize",
        params={
            "client_id": app_ctx["client_id"],
            "redirect_uri": REDIRECT_URI,
            "state": "s",
            "scope": "openid",
            "prompt": "login",
        },
        headers={"Authorization": f"Bearer {token}"},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307)
    assert "/login?next=" in resp.headers["location"]


def test_prompt_none_without_session_returns_login_required_error(client, app_ctx):
    resp = client.get(
        "/auth/authorize",
        params={
            "client_id": app_ctx["client_id"],
            "redirect_uri": REDIRECT_URI,
            "state": "s",
            "scope": "openid",
            "prompt": "none",
        },
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307)
    location = resp.headers["location"]
    assert location.startswith(REDIRECT_URI)
    assert "error=login_required" in location


def test_max_age_exceeded_forces_redirect_to_login(client, app_ctx):
    from app.modules.users.repository import UserRepository

    with Session(test_engine) as session:
        user = UserRepository(session).get_by_id(app_ctx["user_id"])
        user.last_login_at = datetime.now(timezone.utc) - timedelta(seconds=3600)
        session.add(user)
        session.commit()
        token = OIDCService(session).issue_session_token(user.id, user.email, user.full_name)

    resp = client.get(
        "/auth/authorize",
        params={
            "client_id": app_ctx["client_id"],
            "redirect_uri": REDIRECT_URI,
            "state": "s",
            "scope": "openid",
            "max_age": 60,
        },
        headers={"Authorization": f"Bearer {token}"},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307)
    assert "/login?next=" in resp.headers["location"]


def test_max_age_within_window_issues_code(client, app_ctx):
    from app.modules.users.repository import UserRepository

    with Session(test_engine) as session:
        user = UserRepository(session).get_by_id(app_ctx["user_id"])
        token = OIDCService(session).issue_session_token(user.id, user.email, user.full_name)

    resp = client.get(
        "/auth/authorize",
        params={
            "client_id": app_ctx["client_id"],
            "redirect_uri": REDIRECT_URI,
            "state": "s",
            "scope": "openid",
            "max_age": 3600,
        },
        headers={"Authorization": f"Bearer {token}"},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307)
    assert resp.headers["location"].startswith(REDIRECT_URI)
    assert "code=" in resp.headers["location"]
