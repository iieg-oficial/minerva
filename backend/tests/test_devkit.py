import pytest
from sqlalchemy import text
from sqlmodel import Session, select

import app.main as main_module
from app.modules.oidc.models import SigningKey
from tests.conftest import test_engine


@pytest.fixture
def migration_table():
    with test_engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
    yield
    with test_engine.begin() as connection:
        connection.execute(text("DROP TABLE alembic_version"))


def dev_login(client, email="admin@local.dev"):
    resp = client.post("/api/v1/auth/dev-login", json={"email": email})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_ready(client, migration_table, monkeypatch):
    monkeypatch.setattr(main_module, "engine", test_engine)
    with test_engine.begin() as connection:
        for revision in main_module._MIGRATION_HEADS:
            connection.execute(text("INSERT INTO alembic_version VALUES (:revision)"), {"revision": revision})

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_ready_fails_when_database_is_unavailable(client, monkeypatch):
    def fail():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(main_module, "_check_database_readiness", fail)
    assert client.get("/ready").status_code == 503


def test_ready_fails_when_redis_is_unavailable(client, fresh_redis, monkeypatch):
    async def fail():
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr(fresh_redis, "ping", fail)
    monkeypatch.setattr(main_module, "_check_database_readiness", lambda: None)
    assert client.get("/ready").status_code == 503


def test_database_readiness_requires_migrations_and_active_key(client, migration_table, monkeypatch):
    monkeypatch.setattr(main_module, "engine", test_engine)

    with pytest.raises(RuntimeError, match="migrations"):
        main_module._check_database_readiness()

    with test_engine.begin() as connection:
        for revision in main_module._MIGRATION_HEADS:
            connection.execute(text("INSERT INTO alembic_version VALUES (:revision)"), {"revision": revision})
    main_module._check_database_readiness()

    with Session(test_engine) as session:
        for key in session.exec(select(SigningKey)).all():
            session.delete(key)
        session.commit()

    with pytest.raises(RuntimeError, match="signing key"):
        main_module._check_database_readiness()


def test_dev_login_and_me(client):
    token = dev_login(client, "alex@local.dev")
    me = client.get("/api/v1/me", headers=auth(token))
    assert me.status_code == 200
    body = me.json()
    assert body["email"] == "alex@local.dev"
    assert body["status"] == "active"
    assert "id" in body


def test_me_permissions_self_service(client):
    """El endpoint canónico del SDK sigue siendo self-service: un usuario con un rol
    real en una app puede consultar SUS permisos ahí sin ser admin. El rol se otorga
    ANTES del dev-login para que el token emitido incluya esa app en `applications`
    (issue #64: el token solo puede consultar sus propias apps)."""
    from sqlmodel import Session

    from app.modules.applications.models import Application
    from app.modules.users.models import User
    from tests.conftest import grant_role, test_engine

    email = "sdkuser@local.dev"
    with Session(test_engine) as session:
        user = User(email=email, full_name="Sdk User", status="active")
        session.add(user)
        session.flush()
        app_row = Application(name="Sdk App", slug="sdk-app", status="active")
        session.add(app_row)
        session.flush()
        grant_role(session, app_row.id, user.id)
        session.commit()

    token = dev_login(client, email)
    resp = client.get("/api/v1/me/permissions?application=sdk-app", headers=auth(token))
    assert resp.status_code == 200


def test_me_permissions_dev_token_rejects_app_outside_claim(client):
    """Issue #64: un token dev solo autoriza las apps de su claim `applications`;
    pedir permisos de una app en la que el usuario NO tiene rol se rechaza con 403."""
    from sqlmodel import Session

    from app.modules.applications.models import Application
    from tests.conftest import test_engine

    with Session(test_engine) as session:
        session.add(Application(name="Dev App Ajena", slug="dev-app-ajena", status="active"))
        session.commit()

    token = dev_login(client, "sin-acceso@local.dev")
    resp = client.get("/api/v1/me/permissions?application=dev-app-ajena", headers=auth(token))
    assert resp.status_code == 403


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
