"""Tests del issue #11: /authorize exige que el usuario tenga un rol en la app."""

import pytest
from sqlmodel import Session

from app.core.security import hash_secret
from app.modules.applications.models import Application, RedirectURI
from app.modules.auth.service import AuthService
from app.modules.oidc.service import OIDCService
from app.modules.users.models import User
from tests.conftest import grant_role, test_engine

CLIENT_SECRET = "role-gate-secret"
REDIRECT_URI = "https://rolegate.example.com/callback"


@pytest.fixture
def app_ctx():
    with Session(test_engine) as session:
        app_row = Application(
            name="Role Gate App",
            slug="role-gate-app",
            client_secret_hash=hash_secret(CLIENT_SECRET),
            status="active",
        )
        session.add(app_row)
        session.flush()
        session.add(RedirectURI(application_id=app_row.id, uri=REDIRECT_URI, environment="production"))
        session.commit()
        session.refresh(app_row)
        OIDCService(session).ensure_active_signing_key()
        return {"client_id": app_row.client_id, "app_id": app_row.id}


def _create_user(email: str) -> str:
    with Session(test_engine) as session:
        user = User(email=email, full_name="Sin Rol", status="active")
        session.add(user)
        session.commit()
        session.refresh(user)
        return user.id


def test_authorize_denies_user_without_role_in_app(app_ctx):
    user_id = _create_user("sinrol@iieg.gob.mx")
    with Session(test_engine) as session:
        url, reauth_reason = AuthService(session).authorize(
            app_ctx["client_id"], REDIRECT_URI, user_id, "state-1", "openid"
        )
    assert url is None
    assert reauth_reason == "access_denied"


def test_authorize_allows_user_with_role_in_app(app_ctx):
    user_id = _create_user("conrol@iieg.gob.mx")
    with Session(test_engine) as session:
        grant_role(session, app_ctx["app_id"], user_id)
        session.commit()
        url, reauth_reason = AuthService(session).authorize(
            app_ctx["client_id"], REDIRECT_URI, user_id, "state-1", "openid"
        )
    assert reauth_reason is None
    assert url is not None
    assert "code=" in url


def test_authorize_allows_minerva_admin_without_app_role(app_ctx):
    user_id = _create_user("admin-sin-rol-app@iieg.gob.mx")
    with Session(test_engine) as session:
        admin_app = Application(name="Minerva", slug="minerva", status="active")
        session.add(admin_app)
        session.flush()
        grant_role(session, admin_app.id, user_id, slug="minerva.admin")
        session.commit()
        url, reauth_reason = AuthService(session).authorize(
            app_ctx["client_id"], REDIRECT_URI, user_id, "state-1", "openid"
        )
    assert reauth_reason is None
    assert url is not None


def test_authorize_http_redirects_with_access_denied_error(client, app_ctx):
    user_id = _create_user("sinrol-http@iieg.gob.mx")
    with Session(test_engine) as session:
        token = OIDCService(session).issue_session_token(user_id, "sinrol-http@iieg.gob.mx", "Sin Rol")
    resp = client.get(
        "/auth/authorize",
        params={
            "client_id": app_ctx["client_id"],
            "redirect_uri": REDIRECT_URI,
            "state": "s",
            "scope": "openid",
        },
        headers={"Authorization": f"Bearer {token}"},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307)
    location = resp.headers["location"]
    assert location.startswith(REDIRECT_URI)
    assert "error=access_denied" in location
    assert "state=s" in location
