def test_list_users(client, admin_token):
    response = client.get("/users", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data


def test_get_user(client, admin_token, admin_user):
    user_id = admin_user["id"]
    response = client.get(f"/users/{user_id}", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 200
    assert response.json()["email"] == "testadmin@iieg.gob.mx"


def test_update_user_status(client, admin_token, admin_user):
    user_id = admin_user["id"]
    response = client.patch(
        f"/users/{user_id}/status",
        json={"status": "inactive"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "inactive"
