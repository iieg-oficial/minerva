"""Una sola versión para todo el proyecto (issue #89).

La fuente es `version` de `backend/pyproject.toml` — la misma que el tag de release. Las
demás superficies (badge del README, `.env.production.example`, `frontend/package.json`)
la repiten, así que este test es el que se entera cuando una se queda atrás.

`minerva_sdk` **no** entra: versiona en su propio ciclo y esa diferencia es deliberada.
"""

import json
import re
import tomllib
from importlib.metadata import version as package_version
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _pyproject_version() -> str:
    with (REPO / "backend" / "pyproject.toml").open("rb") as f:
        return tomllib.load(f)["project"]["version"]


def test_installed_package_matches_pyproject():
    """`GET /` y `/openapi.json` reportan la metadata del paquete instalado: si quedó
    vieja, la API miente sobre su versión. Al cambiar pyproject hay que reinstalar
    (`pip install -e ".[dev]"`); en CI y en la imagen Docker la instalación es fresca."""
    assert package_version("minerva") == _pyproject_version()


def test_root_and_openapi_report_the_package_version(client):
    """Antes `GET /` traía la versión como literal (se olvidaba en cada release) y
    `/openapi.json` reportaba el 0.1.0 por defecto de FastAPI."""
    assert client.get("/").json()["version"] == _pyproject_version()
    assert client.get("/openapi.json").json()["info"]["version"] == _pyproject_version()


def test_readme_badge_matches_pyproject():
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    badge = re.search(r"badge/versi%C3%B3n-([\d.]+)-", readme)
    assert badge, "no se encontró el badge de versión en el README"
    assert badge.group(1) == _pyproject_version()


def test_production_example_matches_pyproject():
    env = (REPO / ".env.production.example").read_text(encoding="utf-8")
    pinned = re.search(r"^MINERVA_VERSION=(\S+)", env, re.MULTILINE)
    assert pinned, "no se encontró MINERVA_VERSION en .env.production.example"
    assert pinned.group(1) == _pyproject_version()


def test_frontend_package_matches_pyproject():
    package = json.loads((REPO / "frontend" / "package.json").read_text(encoding="utf-8"))
    assert package["version"] == _pyproject_version()
