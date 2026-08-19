import asyncio

import httpx
import pytest
from fastapi import HTTPException
from minerva_sdk import settings

from minerva_example.core import database
from minerva_example.main import app, frontend
from minerva_example.modules.auth.consts import SESSION_COOKIE, STATE_COOKIE
from minerva_example.modules.auth.service import auth_service
from minerva_example.modules.portal import service as portal_service


def request(method: str, path: str, **kwargs) -> httpx.Response:
    async def send():
        cookies = kwargs.pop("cookies", None)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=False,
            cookies=cookies,
        ) as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(send())


@pytest.fixture(autouse=True)
def clean_state():
    original = vars(settings).copy()
    database.pending.clear()
    database.sessions.clear()
    yield
    database.pending.clear()
    database.sessions.clear()
    for key, value in original.items():
        setattr(settings, key, value)


def test_fastapi_mounts_frontend_and_explains_missing_configuration():
    settings.client_id = ""
    config = request("GET", "/api/config")
    route_paths = {route.path for route in app.routes if hasattr(route, "path")}
    assert {"/", "/assets"} <= route_paths
    assert '<script type="module" src="/assets/app.js"' in (frontend / "index.html").read_text()
    assert (frontend / "app.js").is_file()
    assert (frontend / "api.js").is_file()
    assert (frontend / "views.js").is_file()
    assert "[hidden] { display: none !important; }" in (frontend / "app.css").read_text()
    assert config.status_code == 200
    assert "MINERVA_CLIENT_ID" in config.json()["message"]


def test_login_builds_authorization_redirect():
    settings.application_code = "portal_demo"
    settings.client_id = "client-123"
    settings.client_secret = "secret"
    settings.redirect_uri = "http://localhost:8100/callback"
    settings.issuer_url = "http://localhost:3100"
    response = request("GET", "/login")
    assert response.status_code == 307
    assert response.headers["location"].startswith("http://localhost:3100/auth/authorize?")
    assert "prompt=select_account" in response.headers["location"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert len(database.pending) == 1


def test_callback_turns_access_denied_into_a_clear_screen():
    database.pending["state-1"] = "verifier"
    response = request(
        "GET",
        "/callback?state=state-1&error=access_denied",
        cookies={STATE_COOKIE: "state-1"},
    )
    assert response.status_code == 303
    assert "No+tienes+acceso" in response.headers["location"]


def test_callback_rejects_state_from_another_browser():
    database.pending["state-1"] = "verifier"
    response = request(
        "GET",
        "/callback?state=state-1&code=code-1",
        cookies={STATE_COOKIE: "other-state"},
    )
    assert response.status_code == 303
    assert "State+inv%C3%A1lido" in response.headers["location"]
    assert "state-1" in database.pending


def test_callback_creates_an_opaque_http_only_session(monkeypatch):
    database.pending["state-1"] = "verifier"

    async def exchange(code, verifier):
        assert (code, verifier) == ("code-1", "verifier")
        return {"access_token": "access", "refresh_token": "refresh"}

    monkeypatch.setattr(auth_service.oidc, "exchange_code", exchange)
    response = request(
        "GET",
        "/callback?state=state-1&code=code-1",
        cookies={STATE_COOKIE: "state-1"},
    )
    assert response.status_code == 303
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "access" not in response.headers["set-cookie"]
    assert next(iter(database.sessions.values()))["refresh_token"] == "refresh"


def test_protected_route_returns_401_without_session():
    response = request("GET", "/api/whoami")
    assert response.status_code == 401
    assert response.json()["detail"] == "Inicia sesión con Minerva"


def test_protected_route_propagates_missing_permission(monkeypatch):
    database.sessions["sid"] = {"access_token": "token"}

    async def denied(token, permission):
        raise HTTPException(403, f"Requiere permiso: {permission}")

    monkeypatch.setattr(portal_service, "check_permission", denied)
    response = request("GET", "/api/admin", cookies={SESSION_COOKIE: "sid"})
    assert response.status_code == 403
    assert response.json()["detail"] == "Requiere permiso: portal_demo.system.manage"


def test_authorized_views_look_like_a_consumer_system(monkeypatch):
    database.sessions["sid"] = {"access_token": "token"}

    async def allowed(token, permission):
        assert token == "token"
        return {"sub": "user-1", "email": "persona@example.test"}

    monkeypatch.setattr(portal_service, "check_permission", allowed)
    cookies = {SESSION_COOKIE: "sid"}

    documents = request("GET", "/api/documents", cookies=cookies)
    admin = request("GET", "/api/admin", cookies=cookies)

    assert documents.status_code == 200
    assert documents.json()["items"][0]["folio"] == "PD-2026-0042"
    assert admin.status_code == 200
    assert admin.json()["stats"]["Usuarios activos"] == 24


def test_logout_revokes_refresh_and_deletes_local_session(monkeypatch):
    database.sessions["sid"] = {"access_token": "access", "refresh_token": "refresh"}
    revoked = []

    async def revoke(token):
        revoked.append(token)

    monkeypatch.setattr(auth_service.oidc, "revoke", revoke)
    response = request("POST", "/logout", cookies={SESSION_COOKIE: "sid"})
    assert response.status_code == 303
    assert revoked == ["refresh"]
    assert not database.sessions
    assert "Max-Age=0" in response.headers["set-cookie"]
