def dev_login(client, email="admin@local.dev"):
    resp = client.post("/api/v1/auth/dev-login", json={"email": email})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_dev_login_and_me(client):
    token = dev_login(client, "alex@local.dev")
    me = client.get("/api/v1/me", headers=auth(token))
    assert me.status_code == 200
    body = me.json()
    assert body["email"] == "alex@local.dev"
    assert body["status"] == "active"
    assert "id" in body


def test_me_permissions_self_service(client):
    """El endpoint canónico del SDK sigue siendo self-service: un usuario recién
    creado por dev-login puede consultar SUS permisos (vacíos) sin ser admin."""
    token = dev_login(client, "sdkuser@local.dev")
    # La app minerva existe por el seed de los fixtures que la usan; consultamos una
    # app cualquiera registrada. Sin app, responde 404, no 403: no exige admin.
    resp = client.get("/api/v1/me/permissions?application=minerva", headers=auth(token))
    assert resp.status_code in (200, 404)
    assert resp.status_code != 403


def test_me_requires_auth(client):
    assert client.get("/api/v1/me").status_code == 401


# --- R1: el Dev Kit ya NO expone administración ------------------------------
def test_devkit_admin_endpoints_removed(client):
    """El CRUD administrativo que antes colgaba de /api/v1 (y que cualquier token
    de dev-login podía usar para autoasignarse roles) fue retirado: esas rutas ya
    no existen. La administración vive solo en los routers canónicos con admin."""
    token = dev_login(client)
    headers = auth(token)
    assert client.get("/api/v1/applications", headers=headers).status_code == 404
    assert client.get("/api/v1/users", headers=headers).status_code == 404
    assert client.get("/api/v1/roles", headers=headers).status_code == 404
    assert client.get("/api/v1/permissions", headers=headers).status_code == 404
    assert client.get("/api/v1/access-assignments", headers=headers).status_code == 404
    assert client.post("/api/v1/access-assignments", json={}, headers=headers).status_code == 404
    assert client.post("/api/v1/manifests/import", content="x", headers=headers).status_code == 404


def test_non_admin_cannot_self_assign_role(client, non_admin_token):
    """El flujo de escalada (autoasignarse Administrador) queda cerrado: la única
    vía de asignación es el canónico /groups, protegido con require_minerva_admin."""
    resp = client.post(
        "/groups/users/some-user/roles/some-role",
        headers=auth(non_admin_token),
    )
    assert resp.status_code == 403
