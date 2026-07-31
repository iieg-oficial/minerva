"""El backend acepta access tokens RS256 y respeta la blacklist (Fase 7, backend)."""

import pytest
from sqlmodel import Session

from app.core.security import hash_secret
from app.modules.applications.models import Application, RedirectURI
from app.modules.auth.service import AuthService
from app.modules.oidc.service import OIDCService
from app.modules.users.models import User
from tests.conftest import grant_role, test_engine

CLIENT_SECRET = "secret-rs256-auth"
REDIRECT_URI = "https://cli.example.com/cb"


@pytest.fixture
def ctx():
    with Session(test_engine) as session:
        app_row = Application(
            name="RS256 App",
            slug="rs256-app",
            client_secret_hash=hash_secret(CLIENT_SECRET),
            status="active",
        )
        session.add(app_row)
        session.flush()
        session.add(RedirectURI(application_id=app_row.id, uri=REDIRECT_URI, environment="production"))
        user = User(email="rs256@iieg.gob.mx", full_name="RS256 User", status="active")
        session.add(user)
        grant_role(session, app_row.id, user.id)
        session.commit()
        session.refresh(app_row)
        session.refresh(user)
        OIDCService(session).ensure_active_signing_key()
        return {"client_id": app_row.client_id, "user_id": user.id}


def _tokens(client, ctx: dict) -> dict:
    with Session(test_engine) as session:
        url, _ = AuthService(session).authorize(ctx["client_id"], REDIRECT_URI, ctx["user_id"], "s", "openid")
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


def test_rs256_token_accepted_on_me_permissions(client, ctx):
    tokens = _tokens(client, ctx)
    resp = client.get(
        "/api/v1/me/permissions?application=rs256-app",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 200


def test_revoked_token_rejected_on_me_permissions(client, ctx):
    tokens = _tokens(client, ctx)
    # Revoca la sesión: el jti del access token queda en la blacklist.
    client.post(
        "/auth/revoke",
        data={
            "client_id": ctx["client_id"],
            "client_secret": CLIENT_SECRET,
            "token": tokens["refresh_token"],
        },
    )
    resp = client.get(
        "/api/v1/me/permissions?application=rs256-app",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 401


def test_garbage_token_rejected(client):
    resp = client.get(
        "/api/v1/me/permissions?application=rs256-app",
        headers={"Authorization": "Bearer no-es-un-jwt"},
    )
    assert resp.status_code == 401


def test_access_token_rejects_permissions_for_other_application(client, ctx):
    """Issue #64: un access token con aud=A no debe poder consultar permisos de B,
    aunque el usuario SÍ tenga un rol/permiso real ahí (fuga de entitlements)."""
    from app.modules.groups.models import UserRole
    from app.modules.permissions.models import Permission, RolePermission
    from app.modules.roles.models import Role

    with Session(test_engine) as session:
        app_b = Application(name="RS256 App B", slug="rs256-app-b", status="active")
        session.add(app_b)
        session.flush()
        role_b = Role(application_id=app_b.id, name="Member B", slug="member-b")
        session.add(role_b)
        session.flush()
        session.add(UserRole(user_id=ctx["user_id"], role_id=role_b.id))
        perm_b = Permission(application_id=app_b.id, name="Secreto", slug="rs256-app-b.secreto.view")
        session.add(perm_b)
        session.flush()
        session.add(RolePermission(role_id=role_b.id, permission_id=perm_b.id))
        session.commit()

    tokens = _tokens(client, ctx)
    resp = client.get(
        "/api/v1/me/permissions?application=rs256-app-b",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 403
    assert "rs256-app-b.secreto.view" not in resp.text
