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

PG_URL = os.environ.get("MINERVA_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(
    not PG_URL,
    reason="requiere MINERVA_TEST_POSTGRES_URL apuntando a un PostgreSQL real (el trigger es PL/pgSQL)",
)

BACKEND_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def migrated_engine():
    reset_engine = create_engine(PG_URL, isolation_level="AUTOCOMMIT")
    with reset_engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    reset_engine.dispose()

    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": PG_URL},
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
