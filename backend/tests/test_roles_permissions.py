from sqlmodel import Session, select

from app.modules.applications.models import Application
from tests.conftest import test_engine


def test_create_reserved_role_in_foreign_app_is_rejected(client, admin_token):
    app_response = client.post(
        "/applications",
        json={"name": "Ajena", "slug": "ajena"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert app_response.status_code == 201
    response = client.post(
        f"/roles?application_id={app_response.json()['id']}",
        json={"name": "Falso admin", "slug": "minerva.admin"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 400


def test_create_reserved_role_in_minerva_app_is_allowed(client, admin_token):
    with Session(test_engine) as session:
        minerva_app_id = session.exec(select(Application).where(Application.slug == "minerva")).first().id
    response = client.post(
        f"/roles?application_id={minerva_app_id}",
        json={"name": "Auditor", "slug": "minerva.auditor"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 201


def test_create_role(client, admin_token):
    app_response = client.post(
        "/applications",
        json={
            "name": "Role App",
            "slug": "role-test-app",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    app_id = app_response.json()["id"]

    response = client.post(
        f"/roles?application_id={app_id}",
        json={
            "name": "Admin Role",
            "slug": "role-test-app.admin",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 201
    assert response.json()["slug"] == "role-test-app.admin"


def test_create_permission(client, admin_token):
    app_response = client.post(
        "/applications",
        json={
            "name": "Perm App",
            "slug": "perm-test-app",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    app_id = app_response.json()["id"]

    response = client.post(
        f"/permissions?application_id={app_id}",
        json={
            "name": "Create Docs",
            "slug": "perm-test-app.docs.create",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 201
    assert response.json()["slug"] == "perm-test-app.docs.create"


def test_add_permission_to_role(client, admin_token):
    app_response = client.post(
        "/applications",
        json={
            "name": "RBAC App",
            "slug": "rbac-test-app",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    app_id = app_response.json()["id"]

    role_response = client.post(
        f"/roles?application_id={app_id}",
        json={
            "name": "Editor",
            "slug": "rbac-test-app.editor",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    role_id = role_response.json()["id"]

    perm_response = client.post(
        f"/permissions?application_id={app_id}",
        json={
            "name": "Edit Documents",
            "slug": "rbac-test-app.docs.edit",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    perm_id = perm_response.json()["id"]

    response = client.post(
        f"/roles/{role_id}/permissions/{perm_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 201

    list_response = client.get(
        f"/roles/{role_id}/permissions",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert len(list_response.json()) == 1


def test_delete_role_permission(client, admin_token):
    app_response = client.post(
        "/applications",
        json={
            "name": "Delete RBAC",
            "slug": "rbac-del-app",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    app_id = app_response.json()["id"]

    role_response = client.post(
        f"/roles?application_id={app_id}",
        json={
            "name": "ToDelete",
            "slug": "rbac-del-app.todelete",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    role_id = role_response.json()["id"]

    perm_response = client.post(
        f"/permissions?application_id={app_id}",
        json={
            "name": "Temp Permission",
            "slug": "rbac-del-app.temp",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    perm_id = perm_response.json()["id"]

    client.post(f"/roles/{role_id}/permissions/{perm_id}", headers={"Authorization": f"Bearer {admin_token}"})
    response = client.delete(
        f"/roles/{role_id}/permissions/{perm_id}", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 204


def test_add_permission_to_role_rechaza_otra_app(client, admin_token):
    app_a = client.post(
        "/applications",
        json={"name": "Cross App A", "slug": "cross-app-a"},
        headers={"Authorization": f"Bearer {admin_token}"},
    ).json()
    app_b = client.post(
        "/applications",
        json={"name": "Cross App B", "slug": "cross-app-b"},
        headers={"Authorization": f"Bearer {admin_token}"},
    ).json()

    role_response = client.post(
        f"/roles?application_id={app_a['id']}",
        json={"name": "Role A", "slug": "cross-app-a.role"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    role_id = role_response.json()["id"]

    perm_response = client.post(
        f"/permissions?application_id={app_b['id']}",
        json={"name": "Perm B", "slug": "cross-app-b.docs.view"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    perm_id = perm_response.json()["id"]

    response = client.post(
        f"/roles/{role_id}/permissions/{perm_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 400

    list_response = client.get(
        f"/roles/{role_id}/permissions",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert len(list_response.json()) == 0


def test_create_role_concurrent_race_returns_conflict_not_500(client, admin_token, monkeypatch):
    """Issue #76: si la comprobación previa no ve el duplicado (ventana de carrera
    entre dos altas concurrentes), el constraint de BD debe traducirse a 409, no a
    un 500 sin manejar."""
    from app.modules.roles.repository import RoleRepository

    auth = {"Authorization": f"Bearer {admin_token}"}
    app_id = client.post(
        "/applications",
        json={"name": "Role Race App", "slug": "role-race-app"},
        headers=auth,
    ).json()["id"]
    first = client.post(
        f"/roles?application_id={app_id}",
        json={"name": "Admin Role", "slug": "role-race-app.admin"},
        headers=auth,
    )
    assert first.status_code == 201

    monkeypatch.setattr(RoleRepository, "get_by_slug", lambda self, app_id, slug: None)
    resp = client.post(
        f"/roles?application_id={app_id}",
        json={"name": "Admin Role otra vez", "slug": "role-race-app.admin"},
        headers=auth,
    )
    assert resp.status_code == 409, resp.text


def test_create_permission_concurrent_race_returns_conflict_not_500(client, admin_token, monkeypatch):
    """Issue #76: mismo escenario que el rol, para permisos."""
    from app.modules.permissions.repository import PermissionRepository

    auth = {"Authorization": f"Bearer {admin_token}"}
    app_id = client.post(
        "/applications",
        json={"name": "Perm Race App", "slug": "perm-race-app"},
        headers=auth,
    ).json()["id"]
    first = client.post(
        f"/permissions?application_id={app_id}",
        json={"name": "Ver cosa", "slug": "perm-race-app.cosa.view"},
        headers=auth,
    )
    assert first.status_code == 201

    monkeypatch.setattr(PermissionRepository, "get_by_slug", lambda self, app_id, slug: None)
    resp = client.post(
        f"/permissions?application_id={app_id}",
        json={"name": "Ver cosa otra vez", "slug": "perm-race-app.cosa.view"},
        headers=auth,
    )
    assert resp.status_code == 409, resp.text
