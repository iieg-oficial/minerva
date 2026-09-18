"""R11 (fail-closed): un fallo de escritura en Redis durante la invalidación de sesiones
no debe dejar PostgreSQL confirmado a medias.

Antes, `update_user` confirmaba el cambio de credenciales en PG y luego escribía el corte
de invalidación en Redis: si Redis fallaba después del commit, la contraseña ya había
cambiado pero las sesiones vigentes no quedaban invalidadas (fail-open al recuperarse Redis).
Ahora las invalidaciones van a Redis primero y PG se confirma después; si Redis falla, rollback.
"""

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


