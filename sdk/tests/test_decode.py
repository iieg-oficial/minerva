"""Tests de validación de tokens del SDK: RS256/JWKS, aud y anti-confusión de alg."""

import asyncio
import time

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from jose import jwk, jwt

from minerva_sdk import config
from minerva_sdk.fastapi import _decode, _jwks_cache

KID = "test-kid"


def _make_keypair() -> tuple[str, str]:
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = priv.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = (
        priv.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    return private_pem, public_pem


def _jwks_for(public_pem: str) -> dict:
    entry = jwk.construct(public_pem, algorithm="RS256").to_dict()
    entry = {k: (v.decode() if isinstance(v, bytes) else v) for k, v in entry.items()}
    entry.update({"kid": KID, "use": "sig", "alg": "RS256"})
    return {"keys": [entry]}


def _sign(private_pem: str, **claims) -> str:
    payload = {"sub": "u1", "iss": "http://localhost:9000", "exp": int(time.time()) + 300, **claims}
    return jwt.encode(payload, private_pem, algorithm="RS256", headers={"kid": KID})


@pytest.fixture(autouse=True)
def setup():
    private_pem, public_pem = _make_keypair()
    _jwks_cache["jwks"] = _jwks_for(public_pem)  # inyecta el JWKS: sin red
    _jwks_cache["exp"] = time.time() + 3600
    config.settings.application_code = "godin"
    config.settings.verify_aud = True
    config.settings.jwt_secret = ""
    config.settings.expected_issuer = ""
    yield private_pem
    _jwks_cache["jwks"] = None
    _jwks_cache["exp"] = 0.0


def test_valid_rs256_token(setup):
    token = _sign(setup, aud="godin", email="u@iieg.gob.mx")
    payload = asyncio.run(_decode(token))
    assert payload["sub"] == "u1"
    assert payload["aud"] == "godin"


def test_wrong_audience_rejected(setup):
    token = _sign(setup, aud="otra-app")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(_decode(token))
    assert exc.value.status_code == 401


def test_hs256_rejected_when_no_secret(setup):
    # Token HS256 sin secreto configurado → algoritmo no soportado (anti-confusión).
    token = jwt.encode({"sub": "u1", "aud": "godin"}, "secreto-cualquiera", algorithm="HS256")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(_decode(token))
    assert exc.value.status_code == 401
