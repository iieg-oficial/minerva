"""Utilidades compartidas de los tests del SDK: claves RS256 y un doble de red.

El doble reemplaza `httpx.AsyncClient` para que ninguna prueba salga a la red y para
poder contar cuántas veces el SDK llamó a Minerva (clave para probar cachés y cooldowns).
"""

import time

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwk, jwt

from minerva_sdk import config
from minerva_sdk.fastapi import clear_caches

ISSUER = "http://localhost:9000"
APP_CODE = "godin"


def make_keypair() -> tuple[str, str]:
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


def jwks_for(*keys: tuple[str, str]) -> dict:
    """JWKS a partir de pares (kid, public_pem)."""
    entries = []
    for kid, public_pem in keys:
        entry = jwk.construct(public_pem, algorithm="RS256").to_dict()
        entry = {k: (v.decode() if isinstance(v, bytes) else v) for k, v in entry.items()}
        entry.update({"kid": kid, "use": "sig", "alg": "RS256"})
        entries.append(entry)
    return {"keys": entries}


def sign(private_pem: str, kid: str, **claims) -> str:
    payload = {
        "sub": "u1",
        "iss": ISSUER,
        "aud": APP_CODE,
        "typ": "access",
        "exp": int(time.time()) + 300,
        **claims,
    }
    return jwt.encode(payload, private_pem, algorithm="RS256", headers={"kid": kid})


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=httpx.Request("GET", ISSUER),
                response=httpx.Response(self.status_code),
            )


class FakeHTTP:
    """Registra las llamadas salientes y responde con lo que le fije cada test."""

    def __init__(self):
        self.calls: list[dict] = []
        self._jwks: dict = {"keys": []}
        self._permissions = _FakeResponse(200, {"permissions": []})

    def set_jwks(self, jwks: dict) -> None:
        self._jwks = jwks

    def set_permissions(self, permissions: list[str], status_code: int = 200) -> None:
        self._permissions = _FakeResponse(status_code, {"permissions": permissions})

    def count(self, kind: str) -> int:
        return sum(1 for call in self.calls if call["kind"] == kind)

    async def _get(self, url: str, params=None, headers=None) -> _FakeResponse:
        kind = "jwks" if url.endswith("jwks.json") else "permissions"
        self.calls.append({"kind": kind, "url": url, "params": params, "headers": headers})
        return _FakeResponse(200, self._jwks) if kind == "jwks" else self._permissions


@pytest.fixture
def fake_http(monkeypatch) -> FakeHTTP:
    recorder = FakeHTTP()

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            return False

        async def get(self, url, params=None, headers=None):
            return await recorder._get(url, params=params, headers=headers)

    monkeypatch.setattr("minerva_sdk.fastapi.httpx.AsyncClient", _FakeClient)
    return recorder


@pytest.fixture(autouse=True)
def clean_state():
    """Cada test arranca con las cachés vacías y la configuración conocida: son
    globales del módulo y si no, una prueba contamina a la siguiente."""
    clear_caches()
    config.settings.application_code = APP_CODE
    config.settings.issuer_url = ISSUER
    config.settings.expected_issuer = ""
    config.settings.permissions_cache_ttl = 300
    config.settings.jwks_cache_ttl = 3600
    config.settings.jwks_refresh_cooldown = 30
    yield
    clear_caches()
