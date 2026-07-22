"""El seed es idempotente incluso con dos procesos arrancando a la vez.

`Role`/`Permission` no tienen constraint único por `(application_id, slug)`, así que el
get-or-create del seed tiene una carrera real que solo se manifiesta con transacciones
concurrentes de verdad: dos sesiones ven la tabla vacía y duplican rol/permisos. El
advisory lock de transacción de `seed_admin` la cierra. Corre contra el PostgreSQL de
MINERVA_TEST_POSTGRES_URL o se salta (SQLite no tiene ni la función ni concurrencia real).
"""

import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlmodel import Session, select

from app.core.config import settings
from app.core.models import import_models
from app.core.security import hash_password, hash_secret
from app.main import seed_admin
from app.modules.applications.models import Application
from app.modules.groups.models import UserRole
from app.modules.permissions.models import Permission, RolePermission
from app.modules.roles.models import Role
from app.modules.users.models import User
from tests.conftest import require_test_database_url

PG_URL = os.environ.get("MINERVA_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(
    not PG_URL,
    reason="requiere MINERVA_TEST_POSTGRES_URL apuntando a un PostgreSQL real (advisory lock)",
)

BACKEND_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture
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
        env={**os.environ, "DATABASE_URL": PG_URL},
        check=True,
    )

    import_models()
    engine = create_engine(PG_URL, echo=False)
    yield engine
    engine.dispose()


def _count(engine, model) -> int:
    with Session(engine) as session:
        return len(session.exec(select(model)).all())


def test_dos_seeds_concurrentes_no_duplican_rol_ni_permisos(migrated_engine):
    """Estado de partida: admin-user + app minerva creados, pero sin rol/permisos/asignación
    (p. ej. se borró y recreó la app, o un seed previo quedó a medias). Dos procesos corren
    `seed_admin` a la vez; el advisory lock los serializa, así que el resultado debe ser
    exactamente 1 rol, 6 permisos, 6 vínculos y 1 UserRole —sin duplicados."""
    with Session(migrated_engine) as session:
        session.add(
            User(
                email=settings.ADMIN_EMAIL,
                full_name="Administrador Minerva",
                hashed_password=hash_password(settings.ADMIN_PASSWORD),
                status="active",
                domain="iieg.gob.mx",
            )
        )
        session.add(
            Application(
                name="Minerva",
                slug="minerva",
                description="Sistema central de identidad y acceso del IIEG",
                client_id="seed-concurrent-client",
                client_secret_hash=hash_secret("seed-concurrent-secret"),
                status="active",
            )
        )
        session.commit()

    barrier = threading.Barrier(2)
    results: queue.Queue = queue.Queue()

    def _seed():
        try:
            with Session(migrated_engine) as session:
                barrier.wait(timeout=10)  # sueltan juntos: ambos contienden por el lock
                seed_admin(session)
                session.commit()
            results.put(("ok", None))
        except Exception as exc:  # noqa: BLE001 - el test reporta el fallo
            results.put(("error", f"{type(exc).__name__}: {exc}"))

    threads = [threading.Thread(target=_seed) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
        assert not thread.is_alive(), "un seed_admin se quedó bloqueado"

    outcomes = [results.get() for _ in range(2)]
    errors = [value for kind, value in outcomes if kind == "error"]
    assert not errors, f"ningún seed debía fallar, pero: {errors}"

    assert _count(migrated_engine, Role) == 1
    assert _count(migrated_engine, Permission) == 6
    assert _count(migrated_engine, RolePermission) == 6
    assert _count(migrated_engine, UserRole) == 1
