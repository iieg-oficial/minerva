"""Guarda de regresión para R11: Redis debe correr durable (AOF + noeviction).

No es un test de integración con Docker; asserta la config de ambos compose para que
nadie revierta a `allkeys-lru` sin persistencia y vuelva a resucitar tokens revocados
tras un reinicio (ver docs/despliegue.md §3.4).
"""

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMPOSE_FILES = ["docker-compose.yml", "docker-compose.deploy.yml"]


@pytest.mark.parametrize("compose_name", _COMPOSE_FILES)
def test_redis_runs_durable(compose_name: str) -> None:
    content = (_REPO_ROOT / compose_name).read_text(encoding="utf-8")

    assert "--appendonly yes" in content, f"{compose_name}: Redis sin AOF (no sobrevive reinicios)"
    assert "--maxmemory-policy noeviction" in content, f"{compose_name}: Redis puede desalojar revocaciones por LRU"
    assert "allkeys-lru" not in content, f"{compose_name}: regresión a allkeys-lru"
    # El AOF vive en /data: sin volumen persistente, la durabilidad se pierde al recrear el contenedor.
    assert "minerva_redis_data:/data" in content, f"{compose_name}: falta el volumen del AOF"
