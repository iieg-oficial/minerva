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
