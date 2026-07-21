"""La caché de permisos va ligada al token (jti/exp), no al usuario (issue #40).

Antes se indexaba por `(sub, application_code)`: un token revocado seguía autorizando
hasta 300 s, y bastaba con que OTRO token del mismo usuario hubiera poblado la entrada.
"""

import asyncio
import time

import pytest
from fastapi import HTTPException

from minerva_sdk import config
from minerva_sdk.fastapi import (
    _fetch_permissions,
    _permissions_cache,
    clear_caches,
    invalidate_token,
)
from tests.conftest import APP_CODE


def _claims(jti: str | None = "jti-1", exp: int | None = None, sub: str = "u1") -> dict:
    return {"sub": sub, "jti": jti, "exp": exp if exp is not None else int(time.time()) + 300}


def _fetch(claims: dict, token: str = "tok") -> set[str]:
    return asyncio.run(_fetch_permissions(token, claims, APP_CODE))


def test_segunda_llamada_con_el_mismo_token_usa_la_cache(fake_http):
    fake_http.set_permissions(["godin.oficios.create"])
    claims = _claims()

    assert _fetch(claims) == {"godin.oficios.create"}
    assert _fetch(claims) == {"godin.oficios.create"}

    assert fake_http.count("permissions") == 1


def test_dos_tokens_del_mismo_usuario_no_comparten_decision(fake_http):
    """El bug: el segundo token heredaba los permisos cacheados del primero aunque
    fuera otro token (p. ej. uno ya revocado y otro nuevo, o al revés)."""
    fake_http.set_permissions(["godin.oficios.create"])
    assert _fetch(_claims(jti="jti-1")) == {"godin.oficios.create"}

    # Mismo `sub`, token distinto: Minerva vuelve a decidir, y ahora dice que no.
    fake_http.set_permissions([])
    assert _fetch(_claims(jti="jti-2")) == set()

    assert fake_http.count("permissions") == 2


def test_la_entrada_nunca_sobrevive_al_exp_del_token(fake_http):
    """Aunque el TTL configurado sea largo, la caché no puede seguir autorizando
    después de que el token haya expirado."""
    config.settings.permissions_cache_ttl = 3600
    fake_http.set_permissions(["godin.oficios.create"])

    token_exp = int(time.time()) + 30
    _fetch(_claims(jti="jti-corto", exp=token_exp))

    expires_at, _ = _permissions_cache[("jti-corto", APP_CODE)]
    assert expires_at == pytest.approx(token_exp, abs=1)


def test_token_sin_jti_no_se_cachea(fake_http):
    """Fail-closed: sin `jti` no hay forma de ligar la entrada a un token concreto,
    así que se pregunta a Minerva siempre en vez de cachear por usuario."""
    fake_http.set_permissions(["godin.oficios.create"])
    claims = _claims(jti=None)

    _fetch(claims)
    _fetch(claims)

    assert _permissions_cache == {}
    assert fake_http.count("permissions") == 2


def test_un_401_de_minerva_purga_la_entrada(fake_http):
    """Revocar el token debe borrar lo cacheado: si no, un reintento dentro del TTL
    volvería a ver los permisos viejos."""
    fake_http.set_permissions(["godin.oficios.create"])
    claims = _claims(jti="jti-revocado")
    assert _fetch(claims) == {"godin.oficios.create"}
    assert ("jti-revocado", APP_CODE) in _permissions_cache

    fake_http.set_permissions([], status_code=401)
    invalidate_token("jti-revocado")  # simula el logout del consumidor
    with pytest.raises(HTTPException) as exc:
        _fetch(claims)

    assert exc.value.status_code == 401
    assert ("jti-revocado", APP_CODE) not in _permissions_cache


def test_invalidate_token_olvida_solo_ese_token(fake_http):
    fake_http.set_permissions(["godin.oficios.create"])
    _fetch(_claims(jti="jti-1"))
    _fetch(_claims(jti="jti-2"))

    invalidate_token("jti-1")

    assert ("jti-1", APP_CODE) not in _permissions_cache
    assert ("jti-2", APP_CODE) in _permissions_cache


def test_clear_caches_vacia_todo(fake_http):
    fake_http.set_permissions(["godin.oficios.create"])
    _fetch(_claims())

    clear_caches()

    assert _permissions_cache == {}
