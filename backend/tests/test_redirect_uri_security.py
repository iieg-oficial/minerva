import pytest
from cryptography.fernet import Fernet
from sqlmodel import Session, select

from app.core.config import settings
from app.modules.applications.models import Application, RedirectURI
from tests.conftest import test_engine


@pytest.fixture(autouse=True)
def production(monkeypatch):
    monkeypatch.setattr(settings, "MINERVA_KEY_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "MINERVA_MODE", "production")
    monkeypatch.setattr(settings, "APP_ENV", "production")


def _create_app(client, admin_token):
    response = client.post(
        "/applications",
        json={"name": "Redirect Security", "slug": "redirect-security"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.parametrize(
    "uri",
    [
        "http://example.com/callback",
        "custom://example.com/callback",
        "https://user@example.com/callback",
        "https://example.com/callback#fragment",
    ],
)
def test_manual_registration_rejects_insecure_redirect_uris(client, admin_token, uri):
    app = _create_app(client, admin_token)

    response = client.post(
        f"/applications/{app['id']}/redirect-uris",
        json={"uri": uri},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 400


@pytest.mark.parametrize(
    "uri",
    ["https://example.com/callback", "http://localhost/callback", "http://127.0.0.1/callback", "http://[::1]/callback"],
)
def test_manual_registration_accepts_https_and_loopback(client, admin_token, uri):
    app = _create_app(client, admin_token)

    response = client.post(
        f"/applications/{app['id']}/redirect-uris",
        json={"uri": uri},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 201


def test_manifest_rejects_insecure_redirect_uri_before_writing(client, admin_token):
    manifest = """
application:
  code: insecure_manifest
  redirect_uris:
    - http://example.com/callback
"""

    response = client.post(
        "/applications/import-manifest",
        files={"file": ("manifest.minerva.yml", manifest, "application/x-yaml")},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 400
    with Session(test_engine) as session:
        assert session.exec(select(Application).where(Application.slug == "insecure_manifest")).first() is None


def test_authorization_rejects_preexisting_insecure_redirect_uri(client):
    with Session(test_engine) as session:
        app = Application(name="Legacy Insecure", slug="legacy-insecure", status="active")
        session.add(app)
        session.flush()
        session.add(RedirectURI(application_id=app.id, uri="http://example.com/callback"))
        session.commit()
        client_id = app.client_id

    response = client.get(
        "/auth/authorize",
        params={"client_id": client_id, "redirect_uri": "http://example.com/callback", "state": "s"},
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "location" not in response.headers
