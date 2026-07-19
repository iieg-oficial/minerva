def test_register_disabled_returns_403(client, monkeypatch):
    """R4: el registro público está cerrado por defecto (el autouse lo habilita
    para el resto de tests; aquí lo apagamos para verificar el cierre)."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "MINERVA_ENABLE_PUBLIC_REGISTER", False)
    resp = client.post(
        "/auth/register",
        json={"email": "nuevo@iieg.gob.mx", "full_name": "Nuevo", "password": "testpass123"},
    )
    assert resp.status_code == 403


def test_register_rejects_bad_email(client):
    resp = client.post(
        "/auth/register",
        json={"email": "no-es-un-correo", "full_name": "X", "password": "testpass123"},
    )
    assert resp.status_code == 422


def test_register_rejects_short_password(client):
    resp = client.post(
        "/auth/register",
        json={"email": "corto@iieg.gob.mx", "full_name": "X", "password": "1234"},
    )
    assert resp.status_code == 422


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


def test_logout_invalidates_token(client):
    """Logout server-side: tras cerrar sesión, el mismo token queda revocado
    (blacklist por jti) y deja de servir en endpoints protegidos."""
    token = client.post(
        "/auth/register",
        json={"email": "logout_test@iieg.gob.mx", "full_name": "Logout Test", "password": "testpass123"},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/auth/me", headers=headers).status_code == 200
    assert client.post("/auth/logout", headers=headers).status_code == 200
    assert client.get("/auth/me", headers=headers).status_code == 401
