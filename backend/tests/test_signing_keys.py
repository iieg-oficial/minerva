"""Tests de la infraestructura RS256 / JWKS (Fase 1)."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session

from app.core.security import create_access_token_rs256, decode_token_rs256
from app.modules.oidc.service import OIDCService, _generate_rsa_keypair
from tests.conftest import test_engine


@pytest.fixture
def service():
    with Session(test_engine) as session:
        yield OIDCService(session)


def test_generate_and_get_active_key(service):
    key = service.generate_signing_key()
    assert key.status == "active"
    assert key.algorithm == "RS256"
    # La clave privada se guarda cifrada, nunca en texto plano.
    assert "PRIVATE KEY" not in key.private_key_pem

    active = service.get_active_signing_key()
    assert active.kid == key.kid


def test_get_active_raises_when_missing(service):
    with pytest.raises(Exception):
        service.get_active_signing_key()


def test_build_jwks_shape(service):
    key = service.generate_signing_key()
    jwks = service.build_jwks()

    assert len(jwks["keys"]) == 1
    jwk_entry = jwks["keys"][0]
    assert jwk_entry["kid"] == key.kid
    assert jwk_entry["kty"] == "RSA"
    assert jwk_entry["use"] == "sig"
    assert jwk_entry["alg"] == "RS256"


def test_rs256_token_verifies_against_jwks(service):
    service.generate_signing_key()
    kid, private_pem = service.get_active_private_pem()

    token = create_access_token_rs256(
        user_id="user-1", email="u@iieg.gob.mx", name="U", kid=kid, private_key_pem=private_pem
    )
    claims = decode_token_rs256(token, service.build_jwks())

    assert claims["sub"] == "user-1"
    assert claims["email"] == "u@iieg.gob.mx"
    assert "jti" in claims  # necesario para la blacklist (Fase 4.5)


def test_unknown_kid_is_rejected(service):
    service.generate_signing_key()
    jwks = service.build_jwks()

    # Firmar con una clave ajena (kid inexistente en el JWKS).
    foreign_private, _ = _generate_rsa_keypair()
    token = create_access_token_rs256(
        user_id="x", email="x@iieg.gob.mx", name="X", kid="kid-desconocido", private_key_pem=foreign_private
    )

    with pytest.raises(ValueError):
        decode_token_rs256(token, jwks)


def test_rotate_key_retires_previous_and_publishes_both(service):
    first = service.generate_signing_key()
    service.stage_key()
    second = service.promote_key(force=True)

    assert second.kid != first.kid
    assert service.get_active_signing_key().kid == second.kid
    assert service.repo.get_by_kid(first.kid).status == "retired"

    published_kids = {entry["kid"] for entry in service.build_jwks()["keys"]}
    assert {first.kid, second.kid} <= published_kids


def test_purge_retired_before_only_purges_older_than_cutoff(service):
    old_key = service.generate_signing_key()
    service.repo.mark_retired(old_key)
    old_key.rotated_at = datetime.now(timezone.utc) - timedelta(days=1)
    service.session.add(old_key)
    service.session.commit()

    recent_key = service.generate_signing_key()
    service.repo.mark_retired(recent_key)

    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    purged = service.repo.purge_retired_before(cutoff)

    assert purged == 1
    assert service.repo.get_by_kid(old_key.kid) is None
    assert service.repo.get_by_kid(recent_key.kid) is not None


def test_promote_key_purges_retired_keys_past_overlap_window(service):
    stale = service.generate_signing_key()
    service.repo.mark_retired(stale)
    stale.rotated_at = datetime.now(timezone.utc) - timedelta(days=1)
    service.session.add(stale)
    service.session.commit()

    service.generate_signing_key()
    service.stage_key()
    new_active = service.promote_key(force=True)

    assert service.repo.get_by_kid(stale.kid) is None
    assert service.get_active_signing_key().kid == new_active.kid
