"""Verifica que los endpoints del panel exigen el rol minerva.admin."""

from sqlmodel import Session, select

from app.modules.groups.models import UserRole
from app.modules.roles.models import Role
from app.modules.users.models import User
from tests.conftest import test_engine


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


def test_minerva_admin_role_in_foreign_app_does_not_grant_admin(client, admin_token, make_session_token):
    app_response = client.post(
        "/applications",
        json={"name": "Ajena", "slug": "ajena"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert app_response.status_code == 201
    registered = client.post(
        "/auth/register",
        json={"email": "impostor@iieg.gob.mx", "full_name": "Impostor", "password": "testpass123"},
    )
    assert registered.status_code == 201
    client.cookies.clear()
    # Se inserta directo en BD: por API el slug reservado ya no se puede crear fuera de minerva.
    with Session(test_engine) as session:
        user = session.exec(select(User).where(User.email == "impostor@iieg.gob.mx")).first()
        role = Role(application_id=app_response.json()["id"], name="Falso admin", slug="minerva.admin")
        session.add(role)
        session.flush()
        session.add(UserRole(user_id=user.id, role_id=role.id))
        session.commit()

    token = make_session_token("impostor@iieg.gob.mx")
    response = client.get("/users", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
