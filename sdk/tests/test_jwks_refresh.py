"""Refresco del JWKS ante un `kid` desconocido (issue #40).

Sin esto, una rotación de clave en Minerva hacía que el consumidor rechazara tokens
válidos hasta que expirara su caché de JWKS (1 h por defecto).
"""

import asyncio
import time

import pytest
from fastapi import HTTPException

from minerva_sdk import config
from minerva_sdk.fastapi import _decode, _get_jwks, _jwks_cache
from tests.conftest import jwks_for, make_keypair, sign


def test_kid_desconocido_dispara_un_refresco_y_el_token_valida(fake_http):
    """El escenario de la rotación: el consumidor tiene cacheada la clave vieja y
    llega un token firmado con la nueva."""
    old_private, old_public = make_keypair()
    new_private, new_public = make_keypair()

    fake_http.set_jwks(jwks_for(("kid-viejo", old_public)))
    assert asyncio.run(_decode(sign(old_private, "kid-viejo")))["sub"] == "u1"
    assert fake_http.count("jwks") == 1

    # Minerva rotó: ahora publica ambas, pero el consumidor sigue con el caché viejo.
    fake_http.set_jwks(jwks_for(("kid-viejo", old_public), ("kid-nuevo", new_public)))

    assert asyncio.run(_decode(sign(new_private, "kid-nuevo")))["sub"] == "u1"
    assert fake_http.count("jwks") == 2, "debió refrescar el JWKS al ver el kid desconocido"

    # Y el token viejo sigue valiendo, sin volver a pedir el JWKS.
    assert asyncio.run(_decode(sign(old_private, "kid-viejo")))["sub"] == "u1"
    assert fake_http.count("jwks") == 2


def test_kid_conocido_no_vuelve_a_pedir_el_jwks(fake_http):
    private_pem, public_pem = make_keypair()
    fake_http.set_jwks(jwks_for(("kid-1", public_pem)))

    for _ in range(3):
        asyncio.run(_decode(sign(private_pem, "kid-1")))

    assert fake_http.count("jwks") == 1


def test_cooldown_evita_un_refresco_por_request(fake_http):
    """Un `kid` inventado no debe convertir cada request en una llamada a Minerva:
    el endpoint que lo recibe es público y sin autenticar."""
    private_pem, public_pem = make_keypair()
    fake_http.set_jwks(jwks_for(("kid-1", public_pem)))
    asyncio.run(_get_jwks(kid="kid-1"))
    assert fake_http.count("jwks") == 1

    for _ in range(5):
        asyncio.run(_get_jwks(kid="kid-inventado"))

    assert fake_http.count("jwks") == 2, "solo el primer intento debió salir a la red"


def test_pasado_el_cooldown_vuelve_a_intentar(fake_http):
    private_pem, public_pem = make_keypair()
    fake_http.set_jwks(jwks_for(("kid-1", public_pem)))
    asyncio.run(_get_jwks(kid="kid-1"))
    asyncio.run(_get_jwks(kid="kid-desconocido"))
    assert fake_http.count("jwks") == 2

    # El cooldown ya pasó: una rotación posterior no debe quedarse esperando.
    _jwks_cache["retry_after"] = time.time() - 1
    asyncio.run(_get_jwks(kid="kid-desconocido"))

    assert fake_http.count("jwks") == 3


def test_kid_que_no_existe_termina_en_401(fake_http):
    """El refresco no puede volverse un pase libre: si tras refrescar el `kid` sigue
    sin estar, el token se rechaza igual que antes."""
    private_pem, public_pem = make_keypair()
    other_private, _ = make_keypair()
    fake_http.set_jwks(jwks_for(("kid-1", public_pem)))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(_decode(sign(other_private, "kid-que-no-existe")))

    assert exc.value.status_code == 401


def test_cache_expirado_se_recarga_sin_necesidad_de_kid(fake_http):
    private_pem, public_pem = make_keypair()
    fake_http.set_jwks(jwks_for(("kid-1", public_pem)))
    config.settings.jwks_cache_ttl = 0

    asyncio.run(_get_jwks())
    asyncio.run(_get_jwks())

    assert fake_http.count("jwks") == 2
