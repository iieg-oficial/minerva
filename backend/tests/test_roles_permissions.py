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
