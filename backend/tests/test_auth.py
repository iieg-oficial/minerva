def test_register_manual(client):
    response = client.post(
        "/auth/register",
        json={
            "email": "test@example.com",
            "full_name": "Test User",
            "password": "testpass123",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_manual(client):
    client.post(
        "/auth/register",
        json={
            "email": "login_test@example.com",
            "full_name": "Login Test",
            "password": "testpass123",
        },
    )
    response = client.post(
        "/auth/login",
        json={
            "email": "login_test@example.com",
            "password": "testpass123",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_invalid_password(client):
    client.post(
        "/auth/register",
        json={
            "email": "invalid@example.com",
            "full_name": "Invalid Test",
            "password": "correctpass",
        },
    )
    response = client.post(
        "/auth/login",
        json={
            "email": "invalid@example.com",
            "password": "wrongpass",
        },
    )
    assert response.status_code in (400, 401)


def test_get_me(client, admin_token):
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 200
    data = response.json()
    assert "user" in data
    assert data["user"]["email"] == "testadmin@iieg.gob.mx"


def test_get_me_unauthorized(client):
    response = client.get("/auth/me")
    assert response.status_code == 401
