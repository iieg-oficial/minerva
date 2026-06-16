MANIFEST = """
application:
  code: godin
  name: Godín
  description: Gestor de oficios
  base_url: http://localhost:8000
  redirect_uris:
    - http://localhost:8000/auth/callback
permissions:
  - key: godin.oficios.view
    name: Ver oficios
  - key: godin.oficios.create
    name: Crear oficios
roles:
  - name: Consulta
    permissions:
      - godin.oficios.view
  - name: Administrador
    permissions:
      - godin.oficios.view
      - godin.oficios.create
"""


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


def test_manifest_import(client):
    token = dev_login(client)
    resp = client.post("/api/v1/manifests/import", content=MANIFEST, headers=auth(token))
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["application_code"] == "godin"
    assert data["created_application"] is True
    assert data["permissions_upserted"] == 2
    assert data["roles_upserted"] == 2

    # Idempotente: segunda importación no duplica
    resp2 = client.post("/api/v1/manifests/import", content=MANIFEST, headers=auth(token))
    data2 = resp2.json()
    assert data2["created_application"] is False
    assert data2["permissions_upserted"] == 0
    assert data2["roles_upserted"] == 0

    perms = client.get("/api/v1/permissions?application_code=godin", headers=auth(token))
    assert len(perms.json()["items"]) == 2


def test_manifest_validation_rejects_foreign_permission(client):
    token = dev_login(client)
    bad = """
application:
  code: godin
permissions:
  - key: mariachi.database.view
    name: Mal
"""
    resp = client.post("/api/v1/manifests/import", content=bad, headers=auth(token))
    assert resp.status_code == 400


def test_manifest_validation_rejects_bad_convention(client):
    token = dev_login(client)
    bad = """
application:
  code: godin
permissions:
  - key: godin-oficios-view
    name: Mal
"""
    resp = client.post("/api/v1/manifests/import", content=bad, headers=auth(token))
    assert resp.status_code == 400


def test_assign_role_and_check_permissions(client):
    token = dev_login(client)
    client.post("/api/v1/manifests/import", content=MANIFEST, headers=auth(token))

    # usuario nuevo, sin permisos
    me = client.get("/api/v1/me", headers=auth(token))
    user_id = me.json()["id"]

    roles = client.get("/api/v1/roles?application_code=godin", headers=auth(token)).json()["items"]
    admin_role = next(r for r in roles if r["name"] == "Administrador")

    perms_before = client.get("/api/v1/me/permissions?application=godin", headers=auth(token)).json()
    assert perms_before["permissions"] == []

    assignment = client.post(
        "/api/v1/access-assignments",
        json={"user_id": user_id, "role_id": admin_role["id"]},
        headers=auth(token),
    )
    assert assignment.status_code == 201
    assignment_id = assignment.json()["id"]

    perms_after = client.get("/api/v1/me/permissions?application=godin", headers=auth(token)).json()
    assert set(perms_after["permissions"]) == {"godin.oficios.view", "godin.oficios.create"}
    assert perms_after["roles"] == ["Administrador"]

    listing = client.get("/api/v1/access-assignments", headers=auth(token)).json()
    assert any(a["id"] == assignment_id for a in listing)

    deleted = client.delete(f"/api/v1/access-assignments/{assignment_id}", headers=auth(token))
    assert deleted.status_code == 204

    perms_final = client.get("/api/v1/me/permissions?application=godin", headers=auth(token)).json()
    assert perms_final["permissions"] == []


def test_me_requires_auth(client):
    assert client.get("/api/v1/me").status_code == 401
