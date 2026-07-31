"""Tests de los endpoints públicos de descubrimiento OIDC (Fase 2)."""

from sqlmodel import Session

from app.modules.oidc.service import OIDCService
from tests.conftest import test_engine


def _seed_signing_key() -> str:
    """Kid de la clave activa. Es idempotente a propósito: la fixture `client` ya sembró
    una, y desde la migración 009 no puede haber dos claves `active` a la vez."""
    with Session(test_engine) as session:
        return OIDCService(session).ensure_active_signing_key().kid


def test_discovery_document_shape(client):
    resp = client.get("/.well-known/openid-configuration")
    assert resp.status_code == 200

    doc = resp.json()
    assert doc["issuer"]
    assert doc["jwks_uri"].endswith("/.well-known/jwks.json")
    assert doc["authorization_endpoint"].endswith("/auth/authorize")
    assert doc["token_endpoint"].endswith("/auth/token")
    assert doc["userinfo_endpoint"].endswith("/userinfo")
    # Clientes públicos (SPA/móvil sin client_secret) están soportados.
    assert "none" in doc["token_endpoint_auth_methods_supported"]
    # El contrato de firma es RS256: lo que congela el modelo de confianza.
    assert doc["id_token_signing_alg_values_supported"] == ["RS256"]
    assert doc["response_types_supported"] == ["code"]
    assert "openid" in doc["scopes_supported"]
    # Anuncia lo que el servidor realmente soporta: PKCE S256 y refresh tokens.
    assert doc["code_challenge_methods_supported"] == ["S256"]
    assert "refresh_token" in doc["grant_types_supported"]
    # /auth/revoke existe (RFC 7009): debe descubrirse, no quedar implícito.
    assert doc["revocation_endpoint"].endswith("/auth/revoke")
    # claims_supported debe reflejar lo que realmente emiten id_token/userinfo.
    for claim in ("preferred_username", "email_verified", "auth_time", "nonce"):
        assert claim in doc["claims_supported"]
    # roles/permissions son del access token, nunca del id_token ni de /userinfo.
    assert "roles" not in doc["claims_supported"]
    assert "permissions" not in doc["claims_supported"]


def test_jwks_endpoint_publishes_public_key(client):
    kid = _seed_signing_key()

    resp = client.get("/.well-known/jwks.json")
    assert resp.status_code == 200

    keys = resp.json()["keys"]
    assert any(k["kid"] == kid for k in keys)
    entry = next(k for k in keys if k["kid"] == kid)
    assert entry["kty"] == "RSA"
    assert entry["use"] == "sig"
    assert entry["alg"] == "RS256"
    assert entry["n"] and entry["e"]
    # NUNCA debe filtrarse material privado en el JWKS.
    assert "d" not in entry
    assert "p" not in entry


def test_discovery_allows_any_origin_cors(client):
    """Los `.well-known` deben ser legibles desde cualquier origen (CORS abierto)."""
    resp = client.get(
        "/.well-known/openid-configuration",
        headers={"Origin": "https://consumidor.example.com"},
    )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "*"
