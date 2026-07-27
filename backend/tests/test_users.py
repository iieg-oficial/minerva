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


def test_create_user_rechaza_password_vacio_o_corto(client, admin_token):
    """El alta exige una contraseña real: una vacía o menor a 8 caracteres se rechaza
    con 422 antes de llegar al servicio, para no dejar cuentas con contraseña débil."""
    admin_h = {"Authorization": f"Bearer {admin_token}"}
    for password in ("", "corta7"):
        resp = client.post(
            "/users",
            json={"email": f"weak-{len(password)}@iieg.gob.mx", "full_name": "Débil", "password": password},
            headers=admin_h,
        )
        assert resp.status_code == 422, f"contraseña {password!r} debería rechazarse: {resp.text}"


def test_update_user_rechaza_password_corto(client, admin_token, admin_user):
    """El mismo piso aplica al PATCH: cambiar la contraseña a una menor a 8 caracteres
    se rechaza con 422, para no debilitar una cuenta ya existente."""
    resp = client.patch(
        f"/users/{admin_user['id']}",
        json={"password": "corta7"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 422, resp.text


def test_create_user_rechaza_password_mayor_a_72_bytes(client, admin_token):
    """bcrypt 5 lanza ValueError más allá de 72 bytes UTF-8; se rechaza antes con 422
    para no producir un 500 en el alta."""
    admin_h = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post(
        "/users",
        json={"email": "largo@iieg.gob.mx", "full_name": "Largo", "password": "a" * 73},
        headers=admin_h,
    )
    assert resp.status_code == 422, resp.text


def test_create_user_rechaza_full_name_mayor_a_255(client, admin_token):
    """`full_name` es VARCHAR(255) en BD; un valor más largo se rechaza con 422 en vez
    de fallar en el INSERT (el modelo SQLModel no valida `max_length` en runtime)."""
    admin_h = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post(
        "/users",
        json={"email": "nombre-largo@iieg.gob.mx", "full_name": "a" * 256, "password": "pass123456"},
        headers=admin_h,
    )
    assert resp.status_code == 422, resp.text


def test_update_user_rechaza_full_name_mayor_a_255(client, admin_token, admin_user):
    """El mismo piso aplica al PATCH."""
    resp = client.patch(
        f"/users/{admin_user['id']}",
        json={"full_name": "a" * 256},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 422, resp.text


def test_update_user_rechaza_password_mayor_a_72_bytes(client, admin_token, admin_user):
    resp = client.patch(
        f"/users/{admin_user['id']}",
        json={"password": "a" * 73},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 422, resp.text


def _make_user_with_token(client, admin_token, email, make_session_token):
    """Crea un usuario y devuelve (user_id, su_token_de_sesión). Acuña el token
    directamente (el panel es cookie-only: /auth/login ya no devuelve el JWT)."""
    admin_h = {"Authorization": f"Bearer {admin_token}"}
    created = client.post(
        "/users",
        json={"email": email, "full_name": "Victima", "password": "pass123456"},
        headers=admin_h,
    )
    assert created.status_code == 201
    return created.json()["id"], make_session_token(email)


def test_password_change_invalidates_existing_tokens(client, admin_token, make_session_token):
    import time

    admin_h = {"Authorization": f"Bearer {admin_token}"}
    user_id, token = _make_user_with_token(client, admin_token, "victim-pass@iieg.gob.mx", make_session_token)
    user_h = {"Authorization": f"Bearer {token}"}
    assert client.get("/auth/me", headers=user_h).status_code == 200

    # `iat` es entero de segundos: aseguramos que el corte quede DESPUÉS del token.
    time.sleep(1)
    changed = client.patch(f"/users/{user_id}", json={"password": "otra123456"}, headers=admin_h)
    assert changed.status_code == 200

    # El token viejo deja de valer; el del admin (sin cambios) sigue.
    assert client.get("/auth/me", headers=user_h).status_code == 401
    assert client.get("/auth/me", headers=admin_h).status_code == 200


def test_deactivating_user_invalidates_existing_tokens(client, admin_token, make_session_token):
    import time

    admin_h = {"Authorization": f"Bearer {admin_token}"}
    user_id, token = _make_user_with_token(client, admin_token, "victim-status@iieg.gob.mx", make_session_token)
    user_h = {"Authorization": f"Bearer {token}"}
    assert client.get("/auth/me", headers=user_h).status_code == 200

    time.sleep(1)
    changed = client.patch(f"/users/{user_id}/status", json={"status": "inactive"}, headers=admin_h)
    assert changed.status_code == 200

    assert client.get("/auth/me", headers=user_h).status_code == 401
