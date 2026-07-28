"""Constraint compuesto `(application_id, slug/uri)` en roles/permisos/redirect_uris
(issue #76). La carrera real (dos requests concurrentes sin que ninguna vea el commit
de la otra) y la reconciliación de duplicados preexistentes de la migración 011 solo
se pueden probar con transacciones concurrentes de verdad, así que corren contra el
PostgreSQL de MINERVA_TEST_POSTGRES_URL o se saltan (mismo criterio que
test_signing_keys_invariant_pg.py).
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

from app.core.exceptions import ConflictError
from app.core.models import import_models
from app.modules.devkit.manifest import ManifestLoader
from app.modules.groups.models import GroupRole, UserRole
from app.modules.permissions.models import Permission, RolePermission
from app.modules.roles.models import Role
from tests.conftest import require_test_database_url

PG_URL = os.environ.get("MINERVA_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(
    not PG_URL,
    reason="requiere MINERVA_TEST_POSTGRES_URL apuntando a un PostgreSQL real (constraint + carrera real)",
)

BACKEND_DIR = Path(__file__).resolve().parent.parent
PREVIOUS_REVISION = "010_drop_provider_subject"

_APP_ONLY_MANIFEST = """
application:
  code: dedupapp
  name: Dedup App
"""

_MANIFEST = """
application:
  code: dedupapp
  name: Dedup App
  redirect_uris:
    - https://dedupapp.example.com/cb
permissions:
  - key: dedupapp.cosa.view
    name: Ver cosa
roles:
  - name: Lector
    permissions:
      - dedupapp.cosa.view
"""


def _reset_schema() -> None:
    require_test_database_url(PG_URL)
    reset_engine = create_engine(PG_URL, isolation_level="AUTOCOMMIT")
    with reset_engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    reset_engine.dispose()


def _alembic(*args: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": PG_URL},
        check=True,
    )


@pytest.fixture
def migrated_engine():
    _reset_schema()
    _alembic("upgrade", "head")
    import_models()
    engine = create_engine(PG_URL, echo=False)
    yield engine
    engine.dispose()


def _count(engine, model) -> int:
    with Session(engine) as session:
        return len(session.exec(select(model)).all())


def test_concurrent_manifest_imports_leave_one_row_per_key(migrated_engine):
    """Dos importaciones del mismo manifiesto a la vez contra una app YA EXISTENTE:
    ninguna debe dejar filas duplicadas de permisos/roles/redirect_uris, y ninguna debe
    fallar con un error no manejado (a lo sumo un `ConflictError` para el perdedor de la
    carrera). La creación de la app se hace antes, fuera de la carrera: issue #76 es
    sobre roles/permisos/redirect_uris, no sobre `Application` (que ya tenía su propio
    constraint de unicidad antes de este issue, sin relación con este fix)."""
    with Session(migrated_engine) as session:
        ManifestLoader(session).import_manifest(_APP_ONLY_MANIFEST)

    barrier = threading.Barrier(2)
    results: queue.Queue = queue.Queue()

    def _import():
        with Session(migrated_engine) as session:
            barrier.wait(timeout=10)
            try:
                ManifestLoader(session).import_manifest(_MANIFEST)
                results.put(("ok", None))
            except ConflictError as exc:
                results.put(("conflict", str(exc)))
            except Exception as exc:  # noqa: BLE001 - el test reporta cualquier fallo no esperado
                results.put(("error", f"{type(exc).__name__}: {exc}"))

    threads = [threading.Thread(target=_import) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
        assert not thread.is_alive(), "una importación se quedó bloqueada"

    outcomes = [results.get() for _ in range(2)]
    errors = [value for kind, value in outcomes if kind == "error"]
    assert not errors, f"ninguna importación debía fallar sin manejar, pero: {errors}"

    assert _count(migrated_engine, Role) == 1
    assert _count(migrated_engine, Permission) == 1
    with Session(migrated_engine) as session:
        from app.modules.applications.models import RedirectURI

        assert len(session.exec(select(RedirectURI)).all()) == 1


def test_dedupe_migration_reconciles_existing_duplicates_deterministically():
    """Reconciliación de la migración 011: siembra duplicados de rol/permiso/redirect_uri
    con vínculos dependientes que colisionarían al repuntar (mismo escenario verificado a
    mano contra la migración), corre `upgrade head` y confirma que sobrevive exactamente
    una fila por clave, sin perder ni duplicar los vínculos dependientes."""
    _reset_schema()
    _alembic("upgrade", PREVIOUS_REVISION)

    engine = create_engine(PG_URL, echo=False)
    try:
        with engine.begin() as conn:
            conn.execute(
                text("""
                INSERT INTO applications (id, name, slug, client_id, status, created_at, updated_at)
                VALUES ('app-1', 'App Dedup Test', 'dedup-app', 'client-1', 'active', now(), now())
            """)
            )
            conn.execute(
                text("""
                INSERT INTO permissions (id, application_id, name, slug, created_at, updated_at) VALUES
                ('perm-old', 'app-1', 'Ver cosa (vieja)', 'dedup-app.cosa.view', now() - interval '2 days', now()),
                ('perm-new', 'app-1', 'Ver cosa (nueva)', 'dedup-app.cosa.view', now() - interval '1 day', now())
            """)
            )
            conn.execute(
                text("""
                INSERT INTO roles (id, application_id, name, slug, created_at, updated_at) VALUES
                ('role-old', 'app-1', 'Lector (viejo)', 'dedup-app.lector', now() - interval '2 days', now()),
                ('role-new', 'app-1', 'Lector (nuevo)', 'dedup-app.lector', now() - interval '1 day', now())
            """)
            )
            # role-new liga a perm-new y a perm-old (esta última colisiona con el vínculo
            # que role-old ya tiene, tanto al repuntar el rol como al repuntar el permiso).
            conn.execute(text("INSERT INTO role_permissions (role_id, permission_id) VALUES ('role-old', 'perm-old')"))
            conn.execute(text("INSERT INTO role_permissions (role_id, permission_id) VALUES ('role-new', 'perm-new')"))
            conn.execute(text("INSERT INTO role_permissions (role_id, permission_id) VALUES ('role-new', 'perm-old')"))

            conn.execute(
                text("""
                INSERT INTO users (id, email, full_name, status, created_at, updated_at)
                VALUES ('user-1', 'dedup@iieg.gob.mx', 'Usuario Dedup', 'active', now(), now())
            """)
            )
            # user-1 liga a AMBOS roles (colisión al repuntar); un segundo usuario liga
            # solo al duplicado (repunte limpio, sin colisión).
            conn.execute(text("INSERT INTO user_roles (user_id, role_id) VALUES ('user-1', 'role-old')"))
            conn.execute(text("INSERT INTO user_roles (user_id, role_id) VALUES ('user-1', 'role-new')"))
            conn.execute(
                text("""
                INSERT INTO users (id, email, full_name, status, created_at, updated_at)
                VALUES ('user-2', 'dedup2@iieg.gob.mx', 'Usuario Dedup 2', 'active', now(), now())
            """)
            )
            conn.execute(text("INSERT INTO user_roles (user_id, role_id) VALUES ('user-2', 'role-new')"))

            conn.execute(
                text("""
                INSERT INTO groups (id, name, slug, created_at, updated_at)
                VALUES ('group-1', 'Grupo Dedup', 'dedup-group', now(), now())
            """)
            )
            conn.execute(text("INSERT INTO group_roles (group_id, role_id) VALUES ('group-1', 'role-old')"))
            conn.execute(text("INSERT INTO group_roles (group_id, role_id) VALUES ('group-1', 'role-new')"))

            conn.execute(
                text("""
                INSERT INTO redirect_uris (id, application_id, uri, environment) VALUES
                ('uri-1', 'app-1', 'https://dedup-app.example.com/cb', 'production'),
                ('uri-2', 'app-1', 'https://dedup-app.example.com/cb', 'development')
            """)
            )
    finally:
        engine.dispose()

    _alembic("upgrade", "head")

    import_models()
    engine = create_engine(PG_URL, echo=False)
    try:
        with Session(engine) as session:
            roles = session.exec(select(Role).where(Role.application_id == "app-1")).all()
            assert [r.id for r in roles] == ["role-old"]

            perms = session.exec(select(Permission).where(Permission.application_id == "app-1")).all()
            assert [p.id for p in perms] == ["perm-old"]

            from app.modules.applications.models import RedirectURI

            uris = session.exec(select(RedirectURI).where(RedirectURI.application_id == "app-1")).all()
            assert [u.id for u in uris] == ["uri-1"]

            role_perms = session.exec(select(RolePermission)).all()
            assert [(rp.role_id, rp.permission_id) for rp in role_perms] == [("role-old", "perm-old")]

            user_roles = session.exec(select(UserRole)).all()
            assert sorted((ur.user_id, ur.role_id) for ur in user_roles) == [
                ("user-1", "role-old"),
                ("user-2", "role-old"),
            ]

            group_roles = session.exec(select(GroupRole)).all()
            assert [(gr.group_id, gr.role_id) for gr in group_roles] == [("group-1", "role-old")]

        with pytest.raises(Exception, match="uq_roles_application_id_slug"):
            with engine.begin() as conn:
                conn.execute(
                    text("""
                    INSERT INTO roles (id, application_id, name, slug, created_at, updated_at)
                    VALUES ('role-intruso', 'app-1', 'X', 'dedup-app.lector', now(), now())
                """)
                )
    finally:
        engine.dispose()


def test_upgrade_downgrade_upgrade_cycle(migrated_engine):
    """El ciclo completo no debe fallar, y el constraint sigue activo al volver a head."""
    _alembic("downgrade", "-1")
    _alembic("upgrade", "head")

    with pytest.raises(Exception, match="uq_redirect_uris_application_id_uri"):
        with migrated_engine.begin() as conn:
            conn.execute(
                text("""
                INSERT INTO applications (id, name, slug, client_id, status, created_at, updated_at)
                VALUES ('app-cycle', 'Cycle App', 'cycle-app', 'client-cycle', 'active', now(), now())
            """)
            )
            conn.execute(
                text("""
                INSERT INTO redirect_uris (id, application_id, uri, environment) VALUES
                ('uri-a', 'app-cycle', 'https://cycle-app.example.com/cb', 'production'),
                ('uri-b', 'app-cycle', 'https://cycle-app.example.com/cb', 'development')
            """)
            )
