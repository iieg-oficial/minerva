"""R2: cada endpoint acepta solo su clase de token (`typ`). Un access de consumidor
o un dev token no cruzan a los endpoints de panel/admin ni al refresh de sesión."""

import time

from jose import jwt
from sqlmodel import Session

from app.core.security import create_access_token_rs256, create_dev_token_rs256, create_id_token
from app.modules.oidc.service import OIDCService
from tests.conftest import test_engine


def _active_key():
    with Session(test_engine) as session:
        return OIDCService(session).get_active_private_pem()


def _raw_token(**claims):
    """Firma un JWT con la clave activa y claims arbitrarios (para forjar casos que
    los emisores legítimos nunca producen, p. ej. un `iss` ajeno)."""
    kid, pem = _active_key()
    base = {"sub": "u1", "iat": int(time.time()), "exp": int(time.time()) + 300, "jti": "raw-1"}
    return jwt.encode({**base, **claims}, pem, algorithm="RS256", headers={"kid": kid})


def _consumer_access_token(sub="user-x", aud="portal_demo"):
    kid, pem = _active_key()
    return create_access_token_rs256(
        user_id=sub, email="x@iieg.gob.mx", name="X", kid=kid, private_key_pem=pem, application_slug=aud, typ="access"
    )


def _dev_token(sub="user-x"):
    kid, pem = _active_key()
    return create_dev_token_rs256(user_id=sub, email="x@iieg.gob.mx", name="X", kid=kid, private_key_pem=pem)


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_session_token_can_refresh(client, admin_token):
    assert client.post("/auth/refresh", headers=_auth(admin_token)).status_code == 200


def test_consumer_access_token_cannot_refresh(client):
    assert client.post("/auth/refresh", headers=_auth(_consumer_access_token())).status_code == 401


def test_dev_token_cannot_refresh(client):
    assert client.post("/auth/refresh", headers=_auth(_dev_token())).status_code == 401


def test_consumer_access_token_with_admin_sub_cannot_reach_panel(client, admin_user):
    """Aun con el sub de un admin, un access de consumidor no es typ=session: el
    panel lo rechaza antes de mirar el rol."""
    token = _consumer_access_token(sub=admin_user["id"], aud="portal_demo")
    assert client.get("/users", headers=_auth(token)).status_code == 401


def test_consumer_access_token_still_valid_for_self_service(client):
    """No se rompe lo legítimo: el Dev Kit self-service sigue aceptando access/dev
    (no 401 por tipo de token)."""
    assert client.get("/api/v1/me", headers=_auth(_consumer_access_token())).status_code != 401


def test_userinfo_rejects_session_token(client, admin_token):
    """/userinfo solo acepta access de consumidor: una sesión de panel no vale."""
    assert client.get("/userinfo", headers=_auth(admin_token)).status_code == 401


def test_userinfo_rejects_id_token(client):
    kid, pem = _active_key()
    id_token = create_id_token(user_id="u1", client_id="portal_demo", kid=kid, private_key_pem=pem)
    assert client.get("/userinfo", headers=_auth(id_token)).status_code == 401


def test_userinfo_accepts_access_token(client):
    assert client.get("/userinfo", headers=_auth(_consumer_access_token())).status_code == 200


def test_hs256_token_rejected(client, admin_token):
    """Anti-confusión de algoritmo: se reusan los claims EXACTOS de una sesión que sí
    refresca (`test_session_token_can_refresh`, 200) y solo cambia la firma a HS256.
    La validación fija `algorithms=["RS256"]`, así que se rechaza. Es lo que deja sin
    superficie la alerta de `ecdsa`: aquí no entra ninguna firma que no sea RSA."""
    claims = jwt.get_unverified_claims(admin_token)
    kid = jwt.get_unverified_header(admin_token)["kid"]
    token = jwt.encode(claims, "secreto-cualquiera", algorithm="HS256", headers={"kid": kid})
    assert client.post("/auth/refresh", headers=_auth(token)).status_code == 401


def test_wrong_issuer_rejected(client):
    """El backend verifica siempre el `iss`: un token bien firmado pero con issuer
    ajeno se rechaza (una sesión válida re-firmada con otro `iss` no pasa)."""
    token = _raw_token(typ="session", aud="minerva", iss="https://evil.example", email="u@iieg.gob.mx", name="U")
    assert client.post("/auth/refresh", headers=_auth(token)).status_code == 401
