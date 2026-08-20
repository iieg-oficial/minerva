"""La versión del SDK vive en tres sitios y ninguno la vigilaba.

`backend/tests/test_version_alignment.py` alinea el servidor y deja al SDK fuera a propósito
(versiona en su propio ciclo), así que el SDK necesita su propio guardián: si `__version__`,
`pyproject.toml` y el changelog se desincronizan, un consumidor no puede saber qué instaló.
El segundo test es lo que convierte "un cambio incompatible exige entrada de changelog"
(ver "Política de versionado" en README.md) en un gate ejecutable y no en prosa.
"""

import re
from pathlib import Path

import minerva_sdk

SDK_ROOT = Path(__file__).resolve().parent.parent


def _pyproject_version() -> str:
    """Se parsea con regex, no con `tomllib`: el SDK soporta Python 3.10 y ahí no existe."""
    content = (SDK_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "(.+)"$', content, re.MULTILINE)
    assert match, "sdk/pyproject.toml no declara `version`"
    return match.group(1)


def test_la_version_del_paquete_coincide_con_pyproject():
    assert minerva_sdk.__version__ == _pyproject_version()


def test_el_changelog_documenta_la_version_actual():
    changelog = (SDK_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{minerva_sdk.__version__}]" in changelog
