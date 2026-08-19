import asyncio
import base64
import hashlib
from urllib.parse import parse_qs, urlsplit

import pytest

from minerva_sdk.config import MinervaSettings
from minerva_sdk.oidc import MinervaOIDC, MinervaOIDCError


def _settings(**changes) -> MinervaSettings:
    values = {
        "issuer_url": "https://minerva.example",
        "application_code": "mock",
        "client_id": "client-123",
        "client_secret": "secret-123",
        "redirect_uri": "https://mock.example/callback",
    }
    values.update(changes)
    return MinervaSettings(**values)


def test_authorization_request_arma_pkce_y_codifica_urls():
    request = MinervaOIDC(_settings()).authorization_request(prompt="select_account")
    query = parse_qs(urlsplit(request.url).query)

    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(request.code_verifier.encode("ascii")).digest()).rstrip(b"=").decode()
    )
    assert request.url.startswith("https://minerva.example/auth/authorize?")
    assert query["redirect_uri"] == ["https://mock.example/callback"]
    assert query["code_challenge"] == [expected]
    assert query["code_challenge_method"] == ["S256"]
    assert query["prompt"] == ["select_account"]


def test_validate_explains_every_required_login_value():
    config = _settings(issuer_url="localhost:9000", application_code="", client_id="", redirect_uri="")
    with pytest.raises(ValueError) as exc:
        config.validate(login=True)
    message = str(exc.value)
    assert "MINERVA_ISSUER_URL" in message
    assert "MINERVA_APPLICATION_CODE" in message
    assert "MINERVA_CLIENT_ID" in message
    assert "MINERVA_REDIRECT_URI" in message


def test_exchange_omite_secret_en_cliente_publico(monkeypatch):
    calls = []

    class Response:
        is_success = True

        def json(self):
            return {"access_token": "access"}

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, data):
            calls.append((url, data))
            return Response()

    monkeypatch.setattr("minerva_sdk.oidc.httpx.AsyncClient", Client)
    result = asyncio.run(MinervaOIDC(_settings(client_secret="")).exchange_code("code", "verifier"))
    assert result == {"access_token": "access"}
    assert calls[0][0] == "https://minerva.example/auth/token"
    assert "client_secret" not in calls[0][1]


def test_oauth_error_is_actionable(monkeypatch):
    class Response:
        is_success = False
        status_code = 400

        def json(self):
            return {"error": "invalid_grant", "error_description": "Código ya utilizado"}

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, data):
            return Response()

    monkeypatch.setattr("minerva_sdk.oidc.httpx.AsyncClient", Client)
    with pytest.raises(MinervaOIDCError) as exc:
        asyncio.run(MinervaOIDC(_settings()).exchange_code("used", "verifier"))
    assert exc.value.error == "invalid_grant"
    assert exc.value.status_code == 400
    assert str(exc.value) == "Código ya utilizado"
