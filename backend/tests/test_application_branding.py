"""Tests del issue #12: branding público por aplicación para la pantalla de login."""

from sqlmodel import Session, select

from app.modules.applications.models import Application
from tests.conftest import test_engine


def _create_app(client_secret_hash: str = "x", **branding) -> str:
    with Session(test_engine) as session:
        app_row = Application(
            name="Portal Demo",
            slug="portal-demo-branding",
            client_secret_hash=client_secret_hash,
            status="active",
            **branding,
        )
        session.add(app_row)
        session.commit()
        session.refresh(app_row)
        return app_row.client_id


def test_branding_public_endpoint_requires_no_auth(client):
    client_id = _create_app(
        display_name="Portal Documental",
        logo_url="https://cdn.iieg.gob.mx/portal-demo.png",
        brand_color="#5C2472",
    )
    resp = client.get(f"/public/apps/{client_id}/branding")
    assert resp.status_code == 200
    body = resp.json()
    assert body["display_name"] == "Portal Documental"
    assert body["logo_url"] == "https://cdn.iieg.gob.mx/portal-demo.png"
    assert body["brand_color"] == "#5C2472"
    assert body["name"] == "Portal Demo"


def test_branding_never_leaks_secrets(client):
    client_id = _create_app(client_secret_hash="super-secret-hash")
    resp = client.get(f"/public/apps/{client_id}/branding")
    assert resp.status_code == 200
    body = resp.json()
    # Solo datos no sensibles: nada de secreto, redirect_uris, status ni ids internos.
    assert set(body.keys()) == {"name", "display_name", "logo_url", "brand_color"}
    assert "super-secret-hash" not in resp.text


def test_branding_unknown_client_id_returns_404(client):
    resp = client.get("/public/apps/no-existe/branding")
    assert resp.status_code == 404


def test_branding_updatable_via_patch(client, admin_token):
    client_id = _create_app()
    with Session(test_engine) as session:
        app_row = session.exec(select(Application).where(Application.client_id == client_id)).first()
        app_id = app_row.id
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.patch(
        f"/applications/{app_id}",
        json={"display_name": "Nuevo Nombre", "brand_color": "#FF8300"},
        headers=headers,
    )
    assert resp.status_code == 200
    branding = client.get(f"/public/apps/{client_id}/branding").json()
    assert branding["display_name"] == "Nuevo Nombre"
    assert branding["brand_color"] == "#FF8300"
