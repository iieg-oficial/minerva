def test_create_application(client, admin_token):
    response = client.post(
        "/applications",
        json={
            "name": "Test App",
            "slug": "test-app",
            "description": "A test application",
            "homepage_url": "https://test.example.com",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test App"
    assert data["slug"] == "test-app"
    assert "client_id" in data


def test_list_applications(client, admin_token):
    client.post(
        "/applications",
        json={
            "name": "List App",
            "slug": "list-app",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    response = client.get("/applications", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) >= 1


def test_add_redirect_uri(client, admin_token):
    create_response = client.post(
        "/applications",
        json={
            "name": "URI App",
            "slug": "uri-app",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    app_id = create_response.json()["id"]

    response = client.post(
        f"/applications/{app_id}/redirect-uris",
        json={"uri": "https://uri-app.example.com/callback", "environment": "development"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 201
    assert response.json()["uri"] == "https://uri-app.example.com/callback"

    # Contrato: GET devuelve una lista plana (no un objeto paginado con .items). El panel
    # depende de esto para pintar las URIs; si el endpoint regresara a un envoltorio, la lista
    # saldría vacía en el front sin que nadie lo note.
    list_response = client.get(
        f"/applications/{app_id}/redirect-uris",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert list_response.status_code == 200
    uris = list_response.json()
    assert isinstance(uris, list)
    assert [u["uri"] for u in uris] == ["https://uri-app.example.com/callback"]


def test_add_redirect_uri_concurrent_race_returns_conflict_not_500(client, admin_token, monkeypatch):
    """Issue #76: si la comprobación previa no ve el duplicado (ventana de carrera
    entre dos altas concurrentes), el constraint de BD debe traducirse a 409, no a
    un 500 sin manejar."""
    from app.modules.applications.repository import RedirectURIRepository

    auth = {"Authorization": f"Bearer {admin_token}"}
    app_id = client.post(
        "/applications",
        json={"name": "URI Race App", "slug": "uri-race-app"},
        headers=auth,
    ).json()["id"]
    uri = "https://uri-race-app.example.com/callback"
    first = client.post(f"/applications/{app_id}/redirect-uris", json={"uri": uri}, headers=auth)
    assert first.status_code == 201

    monkeypatch.setattr(RedirectURIRepository, "get_by_uri", lambda self, app_id, uri: None)
    resp = client.post(f"/applications/{app_id}/redirect-uris", json={"uri": uri}, headers=auth)
    assert resp.status_code == 409, resp.text


_MANIFEST = """
application:
  code: borrar
  name: App a borrar
permissions:
  - key: borrar.cosa.view
    name: Ver cosa
roles:
  - name: Lector
    permissions:
      - borrar.cosa.view
"""


def _import_manifest(client, admin_token, content, app_id=None):
    url = f"/applications/{app_id}/import-manifest" if app_id else "/applications/import-manifest"
    return client.post(
        url,
        files={"file": ("manifest.minerva.yml", content, "application/x-yaml")},
        headers={"Authorization": f"Bearer {admin_token}"},
    )


def test_delete_application_cascades(client, admin_token):
    auth = {"Authorization": f"Bearer {admin_token}"}
    imp = _import_manifest(client, admin_token, _MANIFEST)
    assert imp.status_code == 200, imp.text
    app_id = imp.json()["application_id"]

    # La importación dejó permisos y roles asociados a la app.
    assert client.get(f"/permissions?application_id={app_id}", headers=auth).json()["items"]
    assert client.get(f"/roles?application_id={app_id}", headers=auth).json()["items"]

    resp = client.delete(f"/applications/{app_id}", headers=auth)
    assert resp.status_code == 204

    # La app y todo lo derivado de ella desaparecen.
    assert client.get(f"/applications/{app_id}", headers=auth).status_code == 404
    assert client.get(f"/permissions?application_id={app_id}", headers=auth).json()["items"] == []
    assert client.get(f"/roles?application_id={app_id}", headers=auth).json()["items"] == []


def test_delete_application_used_removes_tokens(client, admin_token, admin_user):
    """R15: borrar una app ya usada (con auth_codes/refresh_tokens emitidos) no debe
    dejar huérfanos ni violar la FK a applications.client_id. Los audit_logs se conservan
    desligados (application_id=None), no se borran."""
    from datetime import datetime, timedelta, timezone

    from sqlmodel import Session, select

    from app.modules.audit.models import AuditLog
    from app.modules.auth.models import AuthCode, RefreshToken
    from tests.conftest import test_engine

    auth = {"Authorization": f"Bearer {admin_token}"}
    created = client.post("/applications", json={"name": "Used App", "slug": "used-app"}, headers=auth).json()
    app_id, client_id = created["id"], created["client_id"]

    expires = datetime.now(timezone.utc) + timedelta(minutes=5)
    with Session(test_engine) as session:
        session.add(
            AuthCode(code="c-1", client_id=client_id, user_id=admin_user["id"], redirect_uri="x", expires_at=expires)
        )
        session.add(
            RefreshToken(
                token_hash="h-1", family_id="f-1", client_id=client_id, user_id=admin_user["id"], expires_at=expires
            )
        )
        session.add(AuditLog(id="log-1", action="app.delete.test", application_id=app_id))
        session.commit()

    assert client.delete(f"/applications/{app_id}", headers=auth).status_code == 204

    with Session(test_engine) as session:
        assert session.exec(select(AuthCode).where(AuthCode.client_id == client_id)).all() == []
        assert session.exec(select(RefreshToken).where(RefreshToken.client_id == client_id)).all() == []
        log = session.get(AuditLog, "log-1")
        assert log is not None and log.application_id is None


def test_delete_application_not_found(client, admin_token):
    resp = client.delete("/applications/no-existe", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 404


def test_update_manifest_per_app(client, admin_token):
    auth = {"Authorization": f"Bearer {admin_token}"}
    imp = _import_manifest(client, admin_token, _MANIFEST)
    app_id = imp.json()["application_id"]

    extended = """
application:
  code: borrar
  name: App a borrar
permissions:
  - key: borrar.cosa.view
    name: Ver cosa
  - key: borrar.cosa.create
    name: Crear cosa
roles:
  - name: Lector
    permissions:
      - borrar.cosa.view
"""
    resp = _import_manifest(client, admin_token, extended, app_id=app_id)
    assert resp.status_code == 200, resp.text
    assert resp.json()["permissions_upserted"] == 1
    assert len(client.get(f"/permissions?application_id={app_id}", headers=auth).json()["items"]) == 2


def test_update_manifest_rejects_code_mismatch(client, admin_token):
    imp = _import_manifest(client, admin_token, _MANIFEST)
    app_id = imp.json()["application_id"]

    other = _MANIFEST.replace("code: borrar", "code: otra").replace("borrar.cosa", "otra.cosa")
    resp = _import_manifest(client, admin_token, other, app_id=app_id)
    assert resp.status_code == 400


def test_import_manifest_concurrent_race_returns_conflict_not_500(client, admin_token, monkeypatch):
    """Issue #76: dos importaciones del mismo manifiesto pueden solaparse antes de que
    ninguna haga commit. Si la comprobación previa de permisos/roles/redirect_uris no ve
    lo que la otra ya insertó, el constraint de BD debe traducirse a 409, no a un 500."""
    from app.modules.applications.repository import RedirectURIRepository
    from app.modules.permissions.repository import PermissionRepository
    from app.modules.roles.repository import RoleRepository

    first = _import_manifest(client, admin_token, _MANIFEST)
    assert first.status_code == 200

    monkeypatch.setattr(PermissionRepository, "get_by_slug", lambda self, app_id, slug: None)
    monkeypatch.setattr(RoleRepository, "get_by_slug", lambda self, app_id, slug: None)
    monkeypatch.setattr(RedirectURIRepository, "get_by_uri", lambda self, app_id, uri: None)

    resp = _import_manifest(client, admin_token, _MANIFEST)
    assert resp.status_code == 409, resp.text


def test_duplicate_slug(client, admin_token):
    client.post(
        "/applications",
        json={
            "name": "First",
            "slug": "duplicate-slug",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    response = client.post(
        "/applications",
        json={
            "name": "Second",
            "slug": "duplicate-slug",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 409


def test_import_manifest_rejects_foreign_permission(client, admin_token):
    bad = """
application:
  code: godin
permissions:
  - key: mariachi.database.view
    name: Mal
"""
    resp = _import_manifest(client, admin_token, bad)
    assert resp.status_code == 400


def test_import_manifest_rejects_bad_convention(client, admin_token):
    bad = """
application:
  code: godin
permissions:
  - key: godin-oficios-view
    name: Mal
"""
    resp = _import_manifest(client, admin_token, bad)
    assert resp.status_code == 400
