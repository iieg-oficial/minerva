"""`import_models()` debe dejar TODAS las tablas en SQLModel.metadata (issue #73).

Era un no-op: Alembic tomaba una metadata vacía y un `--autogenerate` habría
propuesto borrar el esquema completo.
"""

from sqlmodel import SQLModel

from app.core.models import import_models

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
