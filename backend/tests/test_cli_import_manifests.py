"""El autoimport de manifiestos es un paso único y ruidoso (issue #77).

Antes vivía en el lifespan de FastAPI: con gunicorn corría una vez por worker y
cada fallo se degradaba a `logger.warning`, así que un manifiesto roto pasaba
inadvertido. Ahora es un comando del CLI que el entrypoint ejecuta una sola vez y
que devuelve código ≠ 0 cuando algo falla.
"""

import pytest
from sqlmodel import Session, select

from app import cli
from app.core.config import settings
from app.modules.applications.models import Application
from app.modules.audit.models import AuditLog
from tests.conftest import test_engine

_MANIFEST = """
application:
  code: cliapp
  name: CLI App
permissions:
  - key: cliapp.cosa.view
    name: Ver cosa
roles:
  - name: Lector
    permissions:
      - cliapp.cosa.view
"""

_MANIFEST_INVALIDO = """
application:
  nombre_que_no_existe: si
"""


@pytest.fixture
def manifests_dir(tmp_path, monkeypatch):
    """Apunta el comando al directorio temporal y a la BD de pruebas."""
    monkeypatch.setattr(cli, "engine", test_engine)
    monkeypatch.setattr(settings, "MINERVA_MANIFESTS_PATH", str(tmp_path))
    monkeypatch.setattr(settings, "MINERVA_AUTO_IMPORT_MANIFESTS", True)
    return tmp_path


def test_imports_the_manifests_and_returns_zero(manifests_dir):
    (manifests_dir / "cliapp.minerva.yml").write_text(_MANIFEST, encoding="utf-8")

    assert cli.import_manifests() == 0

    with Session(test_engine) as session:
        assert session.exec(select(Application).where(Application.slug == "cliapp")).first() is not None
        log = session.exec(select(AuditLog).where(AuditLog.action == "manifest_import")).one()

    assert log.event_metadata == {
        "actor": "system",
        "process": "cli",
        "result": "success",
        "source": "cliapp.minerva.yml",
    }


def test_a_broken_manifest_fails_the_step(manifests_dir):
    """El fallo debe ser visible: con `set -e` en el entrypoint, esto aborta el arranque."""
    (manifests_dir / "roto.minerva.yml").write_text(_MANIFEST_INVALIDO, encoding="utf-8")

    assert cli.import_manifests() == 1

    with Session(test_engine) as session:
        log = session.exec(select(AuditLog).where(AuditLog.action == "manifest_import")).one()

    assert log.actor_user_id is None
    assert log.event_metadata["actor"] == "system"
    assert log.event_metadata["result"] == "failure"
    assert "nombre_que_no_existe" not in str(log.event_metadata)


def test_a_broken_manifest_does_not_hide_the_others(manifests_dir):
    (manifests_dir / "a-roto.minerva.yml").write_text(_MANIFEST_INVALIDO, encoding="utf-8")
    (manifests_dir / "b-ok.minerva.yml").write_text(_MANIFEST, encoding="utf-8")

    assert cli.import_manifests() == 1
    with Session(test_engine) as session:
        assert session.exec(select(Application).where(Application.slug == "cliapp")).first() is not None


def test_disabled_autoimport_does_nothing(manifests_dir, monkeypatch):
    monkeypatch.setattr(settings, "MINERVA_AUTO_IMPORT_MANIFESTS", False)
    (manifests_dir / "cliapp.minerva.yml").write_text(_MANIFEST, encoding="utf-8")

    assert cli.import_manifests() == 0
    with Session(test_engine) as session:
        assert session.exec(select(Application).where(Application.slug == "cliapp")).first() is None


def test_lifespan_no_longer_imports_manifests():
    """Guard del invariante del issue: si alguien lo devuelve al arranque de FastAPI,
    vuelve a correr una vez por worker."""
    from app import main

    assert not hasattr(main, "_auto_import_manifests")
