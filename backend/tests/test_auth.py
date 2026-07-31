from app.core.config import settings


def test_register_disabled_returns_403(client, monkeypatch):
    """R4: el registro público está cerrado por defecto (el autouse lo habilita
    para el resto de tests; aquí lo apagamos para verificar el cierre)."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "MINERVA_ENABLE_PUBLIC_REGISTER", False)
    resp = client.post(
        "/auth/register",
        json={"email": "nuevo@iieg.gob.mx", "full_name": "Persona Nueva", "password": "testpass123"},
    )
    assert resp.status_code == 403


def test_register_rejects_bad_email(client):
    resp = client.post(
        "/auth/register",
        json={"email": "no-es-un-correo", "full_name": "Nombre Valido", "password": "testpass123"},
    )
    assert resp.status_code == 422


def test_register_rejects_short_password(client):
    resp = client.post(
        "/auth/register",
        json={"email": "corto@iieg.gob.mx", "full_name": "Nombre Valido", "password": "1234"},
    )
    assert resp.status_code == 422


def test_register_rejects_password_over_72_bytes(client):
    resp = client.post(
        "/auth/register",
        json={"email": "largo@iieg.gob.mx", "full_name": "Nombre Largo", "password": "a" * 73},
    )
    assert resp.status_code == 422


def test_register_accepts_password_of_72_bytes(client):
    resp = client.post(
        "/auth/register",
        json={"email": "limite@iieg.gob.mx", "full_name": "Limite", "password": "a" * 72},
    )
    assert resp.status_code == 201


def test_register_rejects_multibyte_password_over_72_bytes(client):
    # 'ñ' ocupa 2 bytes en UTF-8: 37 repeticiones son 74 bytes aunque len() diga 37.
    resp = client.post(
        "/auth/register",
        json={"email": "multibyte@iieg.gob.mx", "full_name": "Multibyte", "password": "ñ" * 37},
    )
    assert resp.status_code == 422


def test_register_rejects_full_name_over_255_chars(client):
    """`full_name` es VARCHAR(255) en BD; un valor más largo se rechaza con 422 en vez
    de fallar en el INSERT (el modelo SQLModel no valida `max_length` en runtime)."""
    resp = client.post(
        "/auth/register",
        json={"email": "nombre-largo@iieg.gob.mx", "full_name": "a" * 256, "password": "testpass123"},
    )
    assert resp.status_code == 422


def test_register_rejects_full_name_under_6_chars(client):
    resp = client.post(
        "/auth/register",
        json={"email": "nombre-corto@iieg.gob.mx", "full_name": "abcde", "password": "testpass123"},
    )
    assert resp.status_code == 422


def test_login_rejects_password_over_72_bytes(client):
    resp = client.post(
        "/auth/login",
        json={"email": "cualquiera@iieg.gob.mx", "password": "a" * 73},
    )
    assert resp.status_code == 422


def test_email_is_case_insensitive(client):
    """El correo es la identidad: distinto casing no debe crear cuentas duplicadas
    y el login debe funcionar sin importar mayúsculas."""
    first = client.post(
        "/auth/register",
        json={"email": "Alice@iieg.gob.mx", "full_name": "Alice User", "password": "testpass123"},
    )
    assert first.status_code == 201
    dup = client.post(
        "/auth/register",
        json={"email": "alice@iieg.gob.mx", "full_name": "Alice User", "password": "testpass123"},
    )
    assert dup.status_code == 409
    login = client.post("/auth/login", json={"email": "ALICE@iieg.gob.mx", "password": "testpass123"})
    assert login.status_code == 200


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
    # Panel BFF: la respuesta NO trae el JWT; fija la cookie opaca y devuelve descriptor+csrf.
    assert "access_token" not in data
    assert data["csrf"]
    assert data["active"]["email"] == "test@example.com"
    assert response.cookies.get(settings.session_cookie_name)


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
    assert "access_token" not in data
    assert data["csrf"]
    assert response.cookies.get(settings.session_cookie_name)


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


def test_logout_soft_clears_active_account(client):
    """Logout suave del panel: cierra la cuenta activa (la SPA vuelve a login) pero
    NO revoca el token; la cuenta sigue en el contenedor para reingresar. La
    revocación real se prueba en test_panel_session (quitar cuenta / logout-all)."""
    reg = client.post(
        "/auth/register",
        json={"email": "logout_test@iieg.gob.mx", "full_name": "Logout Test", "password": "testpass123"},
    )
    csrf = reg.json()["csrf"]  # la cookie de sesión queda en el jar del TestClient
    assert client.get("/auth/me").status_code == 200

    csrf_headers = {"X-CSRF-Token": csrf, "Origin": settings.FRONTEND_URL}
    assert client.post("/auth/logout", headers=csrf_headers).status_code == 200
    # Sin cuenta activa, el panel queda sin sesión → 401.
    assert client.get("/auth/me").status_code == 401
