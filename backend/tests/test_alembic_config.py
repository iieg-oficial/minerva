"""Alembic y el runtime deben resolver la MISMA base (issue #72).

Antes, `alembic/env.py` leía `DATABASE_URL` directo mientras la aplicación usaba
`effective_db_url`, así que con `MINERVA_DB_URL` definida las migraciones podían
aplicarse a una base distinta de la que sirve Minerva.
"""

import os
import subprocess
import sys
from pathlib import Path

from app.core.config import Settings

BACKEND_DIR = Path(__file__).resolve().parent.parent

# Host inexistente a propósito: no queremos conectar, queremos ver a dónde intenta ir.
UNREACHABLE = "postgresql+psycopg://minerva:minerva@host-inexistente-issue-72:5432/minerva"
OTHER = "postgresql+psycopg://minerva:minerva@otro-host-que-no-debe-usarse:5432/minerva"


def test_effective_db_url_prefers_minerva_db_url():
    settings = Settings(MINERVA_DB_URL=UNREACHABLE, DATABASE_URL=OTHER)
    assert settings.effective_db_url == UNREACHABLE


def test_effective_db_url_normalizes_the_legacy_driver():
    settings = Settings(MINERVA_DB_URL="postgresql://minerva:minerva@db:5432/minerva")
    assert settings.effective_db_url.startswith("postgresql+psycopg://")


def test_alembic_uses_the_same_effective_url_as_the_runtime():
    """Con las dos variables definidas, Alembic debe intentar conectarse a la de
    MINERVA_DB_URL (la efectiva), no a DATABASE_URL."""
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env={**os.environ, "MINERVA_DB_URL": UNREACHABLE, "DATABASE_URL": OTHER},
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "host-inexistente-issue-72" in output
    assert "otro-host-que-no-debe-usarse" not in output
