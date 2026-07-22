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
    _PERMISSIONS_CACHE_MAX,
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


def test_revocar_un_token_deja_de_autorizar_de_inmediato(fake_http):
    """Reproducción del hallazgo original: se autoriza, Minerva revoca el token, y el
    consumidor vuelve a preguntar SIN que nadie invalide nada a mano. Debe dejar de
    autorizar en el acto.

    Es la prueba que decide si la revocación es inmediata: mientras una decisión
    positiva pueda servirse de memoria, aquí se seguirían viendo los permisos viejos.
    """
    fake_http.set_permissions(["godin.oficios.create"])
    claims = _claims()
    assert _fetch(claims) == {"godin.oficios.create"}

    # Minerva revoca el token: su endpoint de permisos empieza a responder 401.
    fake_http.set_permissions([], status_code=401)

    with pytest.raises(HTTPException) as exc:
        _fetch(claims)
    assert exc.value.status_code == 401


def test_sin_cache_cada_chequeo_pregunta_a_minerva(fake_http):
    """El default es no cachear: Minerva es quien aplica la revocación, así que hay que
    consultarla en cada decisión."""
    assert config.settings.permissions_cache_ttl == 0, "el default debe ser sin caché"
    fake_http.set_permissions(["godin.oficios.create"])
    claims = _claims()

    _fetch(claims)
    _fetch(claims)

    assert _permissions_cache == {}
    assert fake_http.count("permissions") == 2


def test_con_cache_activada_la_segunda_llamada_no_sale_a_la_red(fake_http):
    """Opt-in explícito: el consumidor acepta la ventana de propagación a cambio de
    menos tráfico."""
    config.settings.permissions_cache_ttl = 300
    fake_http.set_permissions(["godin.oficios.create"])
    claims = _claims()

    assert _fetch(claims) == {"godin.oficios.create"}
    assert _fetch(claims) == {"godin.oficios.create"}

    assert fake_http.count("permissions") == 1


def test_con_cache_activada_la_revocacion_tarda_hasta_el_ttl(fake_http):
    """Documenta el precio de activar la caché: la revocación deja de ser inmediata.
    Es exactamente el comportamiento que motivó volverla opt-in."""
    config.settings.permissions_cache_ttl = 300
    fake_http.set_permissions(["godin.oficios.create"])
    claims = _claims()
    assert _fetch(claims) == {"godin.oficios.create"}

    fake_http.set_permissions([], status_code=401)

    # El token ya está revocado en Minerva, pero la entrada cacheada lo sigue dejando pasar.
    assert _fetch(claims) == {"godin.oficios.create"}
    assert fake_http.count("permissions") == 1


def test_dos_tokens_del_mismo_usuario_no_comparten_decision(fake_http):
    """El bug: el segundo token heredaba los permisos cacheados del primero aunque
    fuera otro token (p. ej. uno ya revocado y otro nuevo, o al revés)."""
    config.settings.permissions_cache_ttl = 300
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
    config.settings.permissions_cache_ttl = 300
    fake_http.set_permissions(["godin.oficios.create"])
    claims = _claims(jti=None)

    _fetch(claims)
    _fetch(claims)

    assert _permissions_cache == {}
    assert fake_http.count("permissions") == 2


def test_un_401_de_minerva_purga_la_entrada(fake_http):
    """Revocar el token debe borrar lo cacheado: si no, un reintento dentro del TTL
    volvería a ver los permisos viejos."""
    config.settings.permissions_cache_ttl = 300
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
    config.settings.permissions_cache_ttl = 300
    fake_http.set_permissions(["godin.oficios.create"])
    _fetch(_claims(jti="jti-1"))
    _fetch(_claims(jti="jti-2"))

    invalidate_token("jti-1")

    assert ("jti-1", APP_CODE) not in _permissions_cache
    assert ("jti-2", APP_CODE) in _permissions_cache


def test_la_cache_no_crece_sin_cota_con_tokens_vigentes(fake_http):
    """El límite tiene que aguantar el caso incómodo: más de 1000 tokens VIGENTES a la
    vez, donde barrer las vencidas no libera nada. Antes solo se barrían las vencidas,
    así que el tope no existía."""
    config.settings.permissions_cache_ttl = 3600
    fake_http.set_permissions(["godin.oficios.create"])

    total = _PERMISSIONS_CACHE_MAX + 200
    base = int(time.time()) + 3600
    for i in range(total):
        # `exp` creciente: las primeras son las más próximas a vencer.
        _fetch(_claims(jti=f"jti-{i}", exp=base + i))

    assert len(_permissions_cache) <= _PERMISSIONS_CACHE_MAX
    # Se expulsan las más próximas a vencer, no las recién guardadas.
    assert (f"jti-{total - 1}", APP_CODE) in _permissions_cache
    assert ("jti-0", APP_CODE) not in _permissions_cache


def test_las_vencidas_se_barren_antes_de_expulsar_vigentes(fake_http):
    config.settings.permissions_cache_ttl = 3600
    fake_http.set_permissions(["godin.oficios.create"])

    # Llena de entradas ya vencidas, insertadas directo para poder fijar el `exp`.
    for i in range(_PERMISSIONS_CACHE_MAX):
        _permissions_cache[(f"vencida-{i}", APP_CODE)] = (time.time() - 1, frozenset())

    _fetch(_claims(jti="vigente"))

    assert len(_permissions_cache) <= _PERMISSIONS_CACHE_MAX
    assert ("vigente", APP_CODE) in _permissions_cache
    assert not [k for k in _permissions_cache if k[0].startswith("vencida-")]


def test_clear_caches_vacia_todo(fake_http):
    config.settings.permissions_cache_ttl = 300
    fake_http.set_permissions(["godin.oficios.create"])
    _fetch(_claims())

    clear_caches()

    assert _permissions_cache == {}
