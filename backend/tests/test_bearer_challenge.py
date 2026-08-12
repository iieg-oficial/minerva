"""Issue #82 — WWW-Authenticate normativo (RFC 6750 §3) en endpoints Bearer.

Cubre credencial ausente, inválida, expirada e insuficiente, y verifica que los
errores de la sesión por cookie del panel (BFF) NO emiten challenge Bearer.
"""

import pytest
from sqlmodel import Session

from app.core.exceptions import BEARER_ERROR_DESCRIPTIONS
from app.core.security import create_access_token_rs256, hash_secret
from app.modules.applications.models import Application
from app.modules.oidc.service import OIDCService
from app.modules.users.models import User
from tests.conftest import grant_role, test_engine


@pytest.fixture
def ctx():
    with Session(test_engine) as session:
        app_row = Application(
            name="Challenge App",
            slug="challenge-app",
            client_secret_hash=hash_secret("challenge-secret"),
            status="active",
        )
        session.add(app_row)
        session.flush()
        user = User(email="challenge@iieg.gob.mx", full_name="Challenge User", status="active")
        session.add(user)
        grant_role(session, app_row.id, user.id)
        session.commit()
        session.refresh(user)
        oidc = OIDCService(session)
        oidc.ensure_active_signing_key()
        kid, private_pem = oidc.get_active_private_pem()
        return {"user_id": user.id, "kid": kid, "private_pem": private_pem}


def _signed_access_token(ctx: dict, application_slug: str, expires_minutes: int = 15) -> str:
    return create_access_token_rs256(
        user_id=ctx["user_id"],
        email="challenge@iieg.gob.mx",
        name="Challenge User",
        kid=ctx["kid"],
        private_key_pem=ctx["private_pem"],
        application_slug=application_slug,
        expires_minutes=expires_minutes,
        scope="openid",
    )


def _challenge(resp) -> str:
    assert "WWW-Authenticate" in resp.headers, resp.headers
    return resp.headers["WWW-Authenticate"]


# --- Credencial ausente -----------------------------------------------------
@pytest.mark.parametrize("path", ["/userinfo", "/api/v1/me"])
def test_missing_credential_emits_challenge_without_error_code(client, path):
    resp = client.get(path)
    assert resp.status_code == 401
    challenge = _challenge(resp)
    assert challenge == 'Bearer realm="minerva"'


# --- Credencial inválida ----------------------------------------------------
@pytest.mark.parametrize("path", ["/userinfo", "/api/v1/me"])
def test_invalid_token_emits_invalid_token(client, path):
    resp = client.get(path, headers={"Authorization": "Bearer no-es-un-jwt"})
    assert resp.status_code == 401
    challenge = _challenge(resp)
    assert 'error="invalid_token"' in challenge
    # La descripción es fija: no filtra el motivo interno ni depende del `detail`.
    assert f'error_description="{BEARER_ERROR_DESCRIPTIONS["invalid_token"]}"' in challenge


# --- Credencial expirada ----------------------------------------------------
def test_expired_token_emits_invalid_token(client, ctx):
    token = _signed_access_token(ctx, "challenge-app", expires_minutes=-5)
    resp = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
    challenge = _challenge(resp)
    assert 'error="invalid_token"' in challenge
    assert f'error_description="{BEARER_ERROR_DESCRIPTIONS["invalid_token"]}"' in challenge


def test_challenge_does_not_leak_the_failure_reason(client, ctx):
    """Un token expirado y uno malformado producen EL MISMO challenge: el header no
    distingue causas, así un tercero no puede usarlo para sondear tokens ajenos."""
    expired = client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {_signed_access_token(ctx, 'challenge-app', expires_minutes=-5)}"},
    )
    malformed = client.get("/api/v1/me", headers={"Authorization": "Bearer no-es-un-jwt"})
    assert _challenge(expired) == _challenge(malformed)


# --- Credencial válida pero insuficiente ------------------------------------
def test_token_for_another_application_emits_insufficient_scope(client, ctx):
    token = _signed_access_token(ctx, "otra-app")
    resp = client.get("/api/v1/me/permissions?application=challenge-app", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403
    challenge = _challenge(resp)
    assert 'error="insufficient_scope"' in challenge
    assert f'error_description="{BEARER_ERROR_DESCRIPTIONS["insufficient_scope"]}"' in challenge
    # RFC 6750 §3.1: el challenge anuncia el alcance requerido.
    assert 'scope="challenge-app"' in challenge


# --- La sesión por cookie del panel no recibe challenge Bearer --------------
def test_panel_cookie_endpoints_do_not_emit_bearer_challenge(client):
    for path in ["/auth/session", "/users"]:
        resp = client.get(path)
        assert resp.status_code == 401, (path, resp.status_code)
        assert "WWW-Authenticate" not in resp.headers, path
