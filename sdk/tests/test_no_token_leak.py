"""El SDK nunca entrega el bearer dentro del objeto de usuario (issue #40).

Antes `get_current_user` colgaba la credencial cruda en `user["_token"]`: un
`return user` o un log del dict la filtraba. Ahora el dict son solo claims.
"""

import asyncio

import httpx
from conftest import APP_CODE, jwks_for, make_keypair, sign
from fastapi import Depends, FastAPI
from httpx import ASGITransport

from minerva_sdk.fastapi import _decode, get_current_user, require_permission

KID = "kid-leak"


def _values(obj) -> list[str]:
    """Todos los valores del dict, aplanados a texto, para buscar el bearer en
    cualquier campo, no solo en `_token`."""
    return [str(value) for value in obj.values()]


def test_get_current_user_no_devuelve_el_bearer(fake_http):
    private_pem, public_pem = make_keypair()
    fake_http.set_jwks(jwks_for((KID, public_pem)))
    token = sign(private_pem, KID, jti="jti-1")

    user = asyncio.run(get_current_user(_Credentials(token)))

    assert "_token" not in user
    assert token not in _values(user)


def test_decode_devuelve_solo_claims(fake_http):
    private_pem, public_pem = make_keypair()
    fake_http.set_jwks(jwks_for((KID, public_pem)))
    token = sign(private_pem, KID, jti="jti-1", email="u@iieg.gob.mx")

    payload = asyncio.run(_decode(token))

    assert payload["email"] == "u@iieg.gob.mx"
    assert token not in _values(payload)


def test_endpoint_protegido_no_filtra_el_bearer_al_serializar(fake_http):
    """Un consumidor que hace `return user` (el caso que motivó el hallazgo) no debe
    exponer la credencial en la respuesta."""
    private_pem, public_pem = make_keypair()
    fake_http.set_jwks(jwks_for((KID, public_pem)))
    fake_http.set_permissions(["portal_demo.documents.create"])
    token = sign(private_pem, KID, jti="jti-1")

    api = FastAPI()

    @api.get("/protegido")
    async def protegido(user: dict = Depends(require_permission("portal_demo.documents.create", APP_CODE))):
        return user  # exactamente lo que un consumidor descuidado haría

    async def _call():
        # ASGITransport en vez de TestClient: el doble de red reemplaza
        # `httpx.AsyncClient`, y TestClient monta el suyo por dentro. Hablar con la app
        # por ASGI deja esa sustitución limpia y no depende de TestClient.
        transport = ASGITransport(app=api)
        async with httpx.AsyncClient(transport=transport, base_url="http://consumidor") as cli:
            return await cli.get("/protegido", headers={"Authorization": f"Bearer {token}"})

    body = asyncio.run(_call())

    assert body.status_code == 200
    assert token not in body.text
    assert "_token" not in body.json()


class _Credentials:
    """Mínimo `HTTPAuthorizationCredentials` para invocar la dependencia directo."""

    def __init__(self, token: str):
        self.scheme = "Bearer"
        self.credentials = token
