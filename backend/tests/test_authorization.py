def test_check_permission_allowed(client, admin_token):
    app_response = client.post(
        "/applications",
        json={
            "name": "AuthZ App",
            "slug": "authz-test-app",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    app_id = app_response.json()["id"]

    role_response = client.post(
        f"/roles?application_id={app_id}",
        json={
            "name": "Viewer",
            "slug": "authz-test-app.viewer",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    role_id = role_response.json()["id"]

    perm_response = client.post(
        f"/permissions?application_id={app_id}",
        json={
            "name": "View Dashboard",
            "slug": "authz-test-app.dashboard.view",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    perm_id = perm_response.json()["id"]

    client.post(f"/roles/{role_id}/permissions/{perm_id}", headers={"Authorization": f"Bearer {admin_token}"})

    me_response = client.get("/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
    user_id = me_response.json()["user"]["id"]

    client.post(f"/groups/users/{user_id}/roles/{role_id}", headers={"Authorization": f"Bearer {admin_token}"})

    response = client.post(
        "/authorization/check",
        json={
            "user_id": user_id,
            "application_slug": "authz-test-app",
            "permission": "authz-test-app.dashboard.view",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    assert response.json()["allowed"] is True


def test_check_permission_denied(client, admin_token):
    client.post(
        "/applications",
        json={
            "name": "Deny App",
            "slug": "authz-deny-app",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    me_response = client.get("/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
    user_id = me_response.json()["user"]["id"]

    response = client.post(
        "/authorization/check",
        json={
            "user_id": user_id,
            "application_slug": "authz-deny-app",
            "permission": "authz-deny-app.secret.access",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    assert response.json()["allowed"] is False


def test_me_permissions(client, admin_token):
    response = client.get(
        "/authorization/me/permissions?application_slug=unknown",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 404
