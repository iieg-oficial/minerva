"""Verifica que los endpoints del panel exigen el rol minerva.admin."""


def test_non_admin_cannot_list_users(client, non_admin_token):
    response = client.get("/users", headers={"Authorization": f"Bearer {non_admin_token}"})
    assert response.status_code == 403


def test_non_admin_cannot_list_applications(client, non_admin_token):
    response = client.get("/applications", headers={"Authorization": f"Bearer {non_admin_token}"})
    assert response.status_code == 403


def test_admin_can_list_users(client, admin_token):
    response = client.get("/users", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 200


def test_unauthenticated_is_rejected(client):
    response = client.get("/users")
    assert response.status_code == 401


def test_self_service_permissions_not_admin_gated(client, non_admin_token):
    # /authorization/me/permissions es self-service: un usuario sin rol admin
    # debe poder consultar SUS permisos sin recibir 403.
    response = client.get(
        "/authorization/me/permissions",
        params={"application_slug": "minerva"},
        headers={"Authorization": f"Bearer {non_admin_token}"},
    )
    assert response.status_code != 403
