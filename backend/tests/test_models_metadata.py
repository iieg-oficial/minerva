"""`import_models()` debe dejar TODAS las tablas en SQLModel.metadata (issue #73).

Era un no-op: Alembic tomaba una metadata vacía y un `--autogenerate` habría
propuesto borrar el esquema completo.
"""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel

from app.core.models import import_models
from app.modules.users.models import User
from tests.conftest import test_engine

EXPECTED_TABLES = {
    "applications",
    "audit_logs",
    "auth_codes",
    "credential_tokens",
    "groups",
    "group_roles",
    "group_users",
    "manifest_imports",
    "permissions",
    "redirect_uris",
    "refresh_tokens",
    "role_permissions",
    "roles",
    "signing_keys",
    "user_roles",
    "users",
}


def test_import_models_loads_every_table():
    import_models()
    assert EXPECTED_TABLES <= set(SQLModel.metadata.tables)


def test_no_table_is_missing_from_the_expected_set():
    """Si alguien agrega un módulo con tablas, que este test lo obligue a
    declararlo aquí (y, sobre todo, en `import_models`)."""
    import_models()
    assert set(SQLModel.metadata.tables) - EXPECTED_TABLES == set()


def test_users_declares_service_principal_constraints():
    """La migración 014 crea estos constraints con nombre; el modelo los replica para que
    un `--autogenerate` no proponga borrarlos y para que la suite (SQLite) los aplique."""
    import_models()
    names = {c.name for c in SQLModel.metadata.tables["users"].constraints}
    assert {"ck_users_kind", "ck_users_service_without_password", "uq_users_service_application_id"} <= names


def test_service_user_with_password_violates_check():
    with Session(test_engine) as session:
        session.add(User(email="svc@service.minerva.invalid", full_name="Cuenta", kind="service", hashed_password="x"))
        with pytest.raises(IntegrityError):
            session.commit()
