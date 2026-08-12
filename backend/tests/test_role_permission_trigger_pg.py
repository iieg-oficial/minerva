"""Verifica que la migración 007 instala un trigger que bloquea, directamente en
PostgreSQL, los vínculos rol-permiso cruzados entre aplicaciones (issue #38, punto 3).

El trigger es PL/pgSQL: SQLite no lo reproduce. Corre `alembic upgrade head` sobre
un esquema limpio del PostgreSQL apuntado por MINERVA_TEST_POSTGRES_URL, o se salta.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlmodel import Session, select

from app.core.models import import_models
from app.modules.applications.models import Application
from app.modules.permissions.models import Permission, RolePermission
from app.modules.roles.models import Role
from tests.conftest import require_test_database_url

PG_URL = os.environ.get("MINERVA_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(
    not PG_URL,
    reason="requiere MINERVA_TEST_POSTGRES_URL apuntando a un PostgreSQL real (el trigger es PL/pgSQL)",
)

BACKEND_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def migrated_engine():
    require_test_database_url(PG_URL)
    reset_engine = create_engine(PG_URL, isolation_level="AUTOCOMMIT")
    with reset_engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    reset_engine.dispose()

    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        # Las dos: Alembic usa `effective_db_url` y MINERVA_DB_URL tiene prioridad.
        env={**os.environ, "DATABASE_URL": PG_URL, "MINERVA_DB_URL": PG_URL},
        check=True,
    )

    import_models()
    engine = create_engine(PG_URL, echo=False)
    yield engine
    engine.dispose()


def test_trigger_rechaza_insert_cruzado(migrated_engine):
    with Session(migrated_engine) as session:
        app_a = Application(name="Trigger App A", slug="trigger-app-a", status="active")
        app_b = Application(name="Trigger App B", slug="trigger-app-b", status="active")
        session.add(app_a)
        session.add(app_b)
        session.flush()

        role_a = Role(application_id=app_a.id, name="Role A", slug="trigger-app-a.role")
        perm_b = Permission(application_id=app_b.id, name="Perm B", slug="trigger-app-b.docs.view")
        session.add(role_a)
        session.add(perm_b)
        session.commit()
        role_id, perm_id, app_a_id = role_a.id, perm_b.id, app_a.id

        session.add(RolePermission(role_id=role_id, permission_id=perm_id))
        with pytest.raises(Exception, match="misma aplicacion"):
            session.commit()
        session.rollback()

    # El INSERT directo (sin pasar por PermissionService.add_permission_to_role) no dejó
    # rastro: el trigger lo rechazó antes de comitear.
    with Session(migrated_engine) as session:
        linked = session.exec(select(RolePermission).where(RolePermission.role_id == role_id)).all()
        assert linked == []

        # Confirma que sí es posible vincular rol y permiso de la MISMA app (el trigger
        # no bloquea el caso válido).
        perm_a = Permission(application_id=app_a_id, name="Perm A", slug="trigger-app-a.docs.view")
        session.add(perm_a)
        session.commit()
        session.add(RolePermission(role_id=role_id, permission_id=perm_a.id))
        session.commit()


def test_trigger_rechaza_cambiar_application_id(migrated_engine):
    """Un UPDATE directo que mueva un rol o un permiso a otra app dejaría un vínculo
    ya existente en role_permissions cruzado sin que el trigger de esa tabla lo note
    (solo mira INSERT/UPDATE ahí, no en roles/permissions). application_id es inmutable
    por diseño: dos triggers separados en roles y permissions lo bloquean en la base."""
    with Session(migrated_engine) as session:
        app_a = Application(name="Immutable App A", slug="immutable-app-a", status="active")
        app_b = Application(name="Immutable App B", slug="immutable-app-b", status="active")
        session.add(app_a)
        session.add(app_b)
        session.flush()

        role = Role(application_id=app_a.id, name="Role", slug="immutable-app-a.role")
        perm = Permission(application_id=app_a.id, name="Perm", slug="immutable-app-a.docs.view")
        session.add(role)
        session.add(perm)
        session.commit()
        role_id, perm_id, app_a_id, app_b_id = role.id, perm.id, app_a.id, app_b.id

    with Session(migrated_engine) as session:
        role = session.get(Role, role_id)
        role.application_id = app_b_id
        with pytest.raises(Exception, match="application_id es inmutable"):
            session.commit()
        session.rollback()

    with Session(migrated_engine) as session:
        perm = session.get(Permission, perm_id)
        perm.application_id = app_b_id
        with pytest.raises(Exception, match="application_id es inmutable"):
            session.commit()
        session.rollback()

    # Ningún UPDATE se persistió: ambos siguen en la app original.
    with Session(migrated_engine) as session:
        assert session.get(Role, role_id).application_id == app_a_id
        assert session.get(Permission, perm_id).application_id == app_a_id
