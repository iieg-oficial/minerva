"""Atomicidad del borrado de roles (issue #75)."""

import pytest
from sqlmodel import Session, select

from app.modules.applications.models import Application
from app.modules.groups.models import Group, GroupRole, UserRole
from app.modules.permissions.models import Permission, RolePermission
from app.modules.roles.models import Role
from app.modules.roles.repository import RoleRepository
from app.modules.roles.service import RoleService
from app.modules.users.models import User
from tests.conftest import test_engine


@pytest.fixture
def role_ctx():
    with Session(test_engine) as session:
        app_row = Application(name="Role Deletion App", slug="role-deletion-app")
        session.add(app_row)
        session.flush()

        role = Role(application_id=app_row.id, name="ToDelete", slug="role-deletion-app.todelete")
        session.add(role)
        session.flush()

        perm = Permission(application_id=app_row.id, name="Temp", slug="role-deletion-app.temp")
        session.add(perm)
        session.flush()
        session.add(RolePermission(role_id=role.id, permission_id=perm.id))

        user = User(email="role-deletion@iieg.gob.mx", full_name="Role Deletion User", status="active")
        session.add(user)
        session.flush()
        session.add(UserRole(user_id=user.id, role_id=role.id))

        group = Group(name="Role Deletion Group", slug="role-deletion-group")
        session.add(group)
        session.flush()
        session.add(GroupRole(group_id=group.id, role_id=role.id))

        session.commit()
        return {"role_id": role.id}


def _relations_count(role_id: str) -> tuple[int, int, int]:
    with Session(test_engine) as session:
        perms = session.exec(select(RolePermission).where(RolePermission.role_id == role_id)).all()
        users = session.exec(select(UserRole).where(UserRole.role_id == role_id)).all()
        groups = session.exec(select(GroupRole).where(GroupRole.role_id == role_id)).all()
        return len(perms), len(users), len(groups)


def test_fallo_en_borrado_final_revierte_toda_la_limpieza(role_ctx, monkeypatch):
    """Si el borrado final del rol falla, las relaciones ya "limpiadas" no deben
    quedar borradas sin que el rol también se haya ido."""
    role_id = role_ctx["role_id"]

    def _boom(*args, **kwargs):
        raise RuntimeError("fallo simulado en el borrado final")

    monkeypatch.setattr(RoleRepository, "delete", _boom)

    with Session(test_engine) as session:
        with pytest.raises(RuntimeError):
            RoleService(session).delete_role(role_id)

    assert _relations_count(role_id) == (1, 1, 1)
    with Session(test_engine) as session:
        assert RoleRepository(session).get_by_id(role_id) is not None


def test_borrado_exitoso_elimina_todas_las_relaciones(role_ctx):
    role_id = role_ctx["role_id"]

    with Session(test_engine) as session:
        RoleService(session).delete_role(role_id)

    assert _relations_count(role_id) == (0, 0, 0)
    with Session(test_engine) as session:
        assert RoleRepository(session).get_by_id(role_id) is None
