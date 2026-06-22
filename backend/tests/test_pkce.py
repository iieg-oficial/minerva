"""Tests de PKCE (RFC 7636) y binding del authorization code (Fase 3)."""

import base64
import hashlib

import pytest
from sqlmodel import Session

from app.core.exceptions import BadRequestError
from app.core.security import hash_secret, verify_pkce
from app.modules.applications.models import Application, RedirectURI
from app.modules.auth.service import AuthService
from app.modules.oidc.service import OIDCService
from app.modules.users.models import User
from tests.conftest import test_engine

CLIENT_SECRET = "secret-de-prueba"
REDIRECT_URI = "https://app.example.com/callback"
# Vector de prueba del RFC 7636, apéndice B.
RFC_VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
RFC_CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _code_from_url(url: str) -> str:
    return url.split("code=")[1].split("&")[0]


@pytest.fixture
def seeded():
    with Session(test_engine) as session:
        app_row = Application(
            name="PKCE App",
            slug="pkce-app",
            client_secret_hash=hash_secret(CLIENT_SECRET),
            status="active",
        )
        session.add(app_row)
        session.flush()
        session.add(RedirectURI(application_id=app_row.id, uri=REDIRECT_URI, environment="production"))
        user = User(email="pkce@iieg.gob.mx", full_name="PKCE User", auth_provider="local", status="active")
        session.add(user)
        session.commit()
        session.refresh(app_row)
        session.refresh(user)
        # El canje firma access token (RS256) e id_token: requiere clave activa.
        OIDCService(session).ensure_active_signing_key()
        return {"client_id": app_row.client_id, "user_id": user.id}


def test_verify_pkce_rfc_vector():
    assert verify_pkce(RFC_VERIFIER, RFC_CHALLENGE)
    assert not verify_pkce("verifier-equivocado", RFC_CHALLENGE)


def test_pkce_happy_path(seeded):
    challenge = _challenge(RFC_VERIFIER)
    with Session(test_engine) as session:
        svc = AuthService(session)
        url = svc.authorize(
            seeded["client_id"],
            REDIRECT_URI,
            seeded["user_id"],
            "state-1",
            "openid",
            code_challenge=challenge,
            code_challenge_method="S256",
        )
        result = svc.exchange_token(seeded["client_id"], CLIENT_SECRET, _code_from_url(url), REDIRECT_URI, RFC_VERIFIER)
    assert "access_token" in result


def test_pkce_wrong_verifier_rejected(seeded):
    challenge = _challenge(RFC_VERIFIER)
    with Session(test_engine) as session:
        svc = AuthService(session)
        url = svc.authorize(
            seeded["client_id"], REDIRECT_URI, seeded["user_id"], "s", "openid", code_challenge=challenge
        )
        with pytest.raises(BadRequestError):
            svc.exchange_token(seeded["client_id"], CLIENT_SECRET, _code_from_url(url), REDIRECT_URI, "otro-verifier")


def test_pkce_missing_verifier_rejected(seeded):
    challenge = _challenge(RFC_VERIFIER)
    with Session(test_engine) as session:
        svc = AuthService(session)
        url = svc.authorize(
            seeded["client_id"], REDIRECT_URI, seeded["user_id"], "s", "openid", code_challenge=challenge
        )
        with pytest.raises(BadRequestError):
            svc.exchange_token(seeded["client_id"], CLIENT_SECRET, _code_from_url(url), REDIRECT_URI, None)


def test_authorize_rejects_plain_method(seeded):
    with Session(test_engine) as session:
        svc = AuthService(session)
        with pytest.raises(BadRequestError):
            svc.authorize(
                seeded["client_id"],
                REDIRECT_URI,
                seeded["user_id"],
                "s",
                "openid",
                code_challenge=_challenge(RFC_VERIFIER),
                code_challenge_method="plain",
            )


def test_confidential_client_without_pkce_still_works(seeded):
    """Compatibilidad: un cliente confidencial sin challenge no necesita verifier."""
    with Session(test_engine) as session:
        svc = AuthService(session)
        url = svc.authorize(seeded["client_id"], REDIRECT_URI, seeded["user_id"], "s", "openid")
        result = svc.exchange_token(seeded["client_id"], CLIENT_SECRET, _code_from_url(url), REDIRECT_URI)
    assert "access_token" in result


def test_exchange_rejects_redirect_uri_mismatch(seeded):
    with Session(test_engine) as session:
        svc = AuthService(session)
        url = svc.authorize(seeded["client_id"], REDIRECT_URI, seeded["user_id"], "s", "openid")
        with pytest.raises(BadRequestError):
            svc.exchange_token(
                seeded["client_id"], CLIENT_SECRET, _code_from_url(url), "https://malicioso.example.com/callback"
            )
