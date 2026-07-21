"""Matriz de callbacks de /authorize: la URL de vuelta al consumidor se arma con
`urlencode`, preserva la query que la `redirect_uri` registrada ya traiga y devuelve el
`state` byte-for-byte. Incluye la validación de `response_type`.

Todo se verifica parseando la URL (`urlsplit`/`parse_qs`), nunca por substring: el bug
que se corrige aquí era precisamente de forma de la URL, así que compararla como texto
plano dejaría pasar la regresión.
"""

from urllib.parse import parse_qs, urlsplit

import pytest
from sqlmodel import Session, select

from app.core.security import hash_secret
from app.modules.applications.models import Application, RedirectURI
from app.modules.auth.models import AuthCode
from app.modules.oidc.service import OIDCService
from app.modules.users.models import User
from tests.conftest import grant_role, test_engine

CLIENT_SECRET = "callbacks-secret"
REDIRECT_PLAIN = "https://callbacks.example.com/cb"
REDIRECT_QUERY = "https://callbacks.example.com/cb?tenant=jal&lang=es"
# Cubre todo lo que la concatenación cruda rompía: espacio, separadores de query y
# fragmento. Un cliente compara el state que vuelve con el que mandó (anti-CSRF).
STATE_RESERVADO = "a b&c=d/e?f#g+h%20i"


@pytest.fixture
def app_ctx():
    with Session(test_engine) as session:
        app_row = Application(
            name="Callbacks App",
            slug="callbacks-app",
            client_secret_hash=hash_secret(CLIENT_SECRET),
            status="active",
        )
        session.add(app_row)
        session.flush()
        for uri in (REDIRECT_PLAIN, REDIRECT_QUERY):
            session.add(RedirectURI(application_id=app_row.id, uri=uri, environment="production"))

        con_rol = User(email="con-rol@iieg.gob.mx", full_name="Con Rol", auth_provider="local", status="active")
        sin_rol = User(email="sin-rol@iieg.gob.mx", full_name="Sin Rol", auth_provider="local", status="active")
        session.add(con_rol)
        session.add(sin_rol)
        session.flush()
        grant_role(session, app_row.id, con_rol.id)
        session.commit()

        oidc = OIDCService(session)
        oidc.ensure_active_signing_key()
        return {
            "client_id": app_row.client_id,
            "token": oidc.issue_session_token(con_rol.id, con_rol.email, con_rol.full_name),
            "token_sin_rol": oidc.issue_session_token(sin_rol.id, sin_rol.email, sin_rol.full_name),
        }


def _query(url: str) -> dict[str, list[str]]:
    return parse_qs(urlsplit(url).query, keep_blank_values=True)


def _sin_query(url: str) -> str:
    """La URL sin su query: sirve para comprobar que el destino no se alteró."""
    return urlsplit(url)._replace(query="").geturl()


def _authorize(client, ctx, token: str | None = None, **params) -> str:
    """Llama a /authorize y devuelve el `Location`."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    resp = client.get(
        "/auth/authorize",
        params={"client_id": ctx["client_id"], "scope": "openid", **params},
        headers=headers,
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307), resp.text
    return resp.headers["location"]


def _authorize_url(client, ctx, token: str, **params) -> str:
    """Variante JSON que consume la SPA. Debe devolver exactamente lo mismo."""
    resp = client.get(
        "/auth/authorize/url",
        params={"client_id": ctx["client_id"], "scope": "openid", **params},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["redirect_url"]


def _codes_emitidos() -> int:
    with Session(test_engine) as session:
        return len(session.exec(select(AuthCode)).all())


def test_el_callback_conserva_la_query_previa_de_la_redirect_uri(client, app_ctx):
    """Una redirect_uri registrada con query propia no debe quedar con dos `?`."""
    location = _authorize(client, app_ctx, app_ctx["token"], redirect_uri=REDIRECT_QUERY, state="s")

    assert location.count("?") == 1
    assert _sin_query(location) == "https://callbacks.example.com/cb"
    params = _query(location)
    assert params["tenant"] == ["jal"]
    assert params["lang"] == ["es"]
    assert len(params["code"][0]) > 0
    assert params["state"] == ["s"]


def test_el_state_con_caracteres_reservados_vuelve_identico(client, app_ctx):
    location = _authorize(client, app_ctx, app_ctx["token"], redirect_uri=REDIRECT_PLAIN, state=STATE_RESERVADO)

    assert _query(location)["state"] == [STATE_RESERVADO]


def test_el_state_reservado_tambien_vuelve_identico_con_query_previa(client, app_ctx):
    """Los dos arreglos combinados: la query previa se conserva y el state no se
    contamina con los separadores que él mismo contiene."""
    location = _authorize(client, app_ctx, app_ctx["token"], redirect_uri=REDIRECT_QUERY, state=STATE_RESERVADO)

    params = _query(location)
    assert params["state"] == [STATE_RESERVADO]
    assert params["tenant"] == ["jal"]
    assert "code" in params


def test_response_type_no_soportado_devuelve_error_sin_emitir_codigo(client, app_ctx):
    """`token`/`id_token` no están soportados (el discovery ya declara solo `code`):
    debe volver el error estándar al cliente, no un `code` como si nada."""
    location = _authorize(
        client,
        app_ctx,
        app_ctx["token"],
        redirect_uri=REDIRECT_QUERY,
        state=STATE_RESERVADO,
        response_type="token",
    )

    params = _query(location)
    assert params["error"] == ["unsupported_response_type"]
    assert params["state"] == [STATE_RESERVADO]
    assert params["tenant"] == ["jal"]
    assert "code" not in params
    assert _codes_emitidos() == 0


def test_response_type_no_soportado_se_rechaza_aunque_no_haya_sesion(client, app_ctx):
    """El error del cliente se resuelve antes de mandar al usuario a login: no tiene
    sentido hacerle autenticarse para luego rechazar la solicitud."""
    location = _authorize(client, app_ctx, redirect_uri=REDIRECT_PLAIN, state="s", response_type="id_token")

    assert _query(location)["error"] == ["unsupported_response_type"]


@pytest.mark.parametrize("extra", [{}, {"response_type": "code"}])
def test_response_type_code_explicito_o_por_defecto_emite_codigo(client, app_ctx, extra):
    location = _authorize(client, app_ctx, app_ctx["token"], redirect_uri=REDIRECT_PLAIN, state="s", **extra)

    assert "code" in _query(location)
    assert _codes_emitidos() == 1


def test_access_denied_respeta_la_query_previa_y_el_state(client, app_ctx):
    location = _authorize(
        client,
        app_ctx,
        app_ctx["token_sin_rol"],
        redirect_uri=REDIRECT_QUERY,
        state=STATE_RESERVADO,
    )

    params = _query(location)
    assert params["error"] == ["access_denied"]
    assert params["state"] == [STATE_RESERVADO]
    assert params["tenant"] == ["jal"]
    assert "code" not in params


def test_login_required_respeta_la_query_previa_y_el_state(client, app_ctx):
    """Sin sesión y con `prompt=none` no se puede pedir login: vuelve el error."""
    location = _authorize(
        client,
        app_ctx,
        redirect_uri=REDIRECT_QUERY,
        state=STATE_RESERVADO,
        prompt="none",
    )

    params = _query(location)
    assert params["error"] == ["login_required"]
    assert params["state"] == [STATE_RESERVADO]
    assert params["tenant"] == ["jal"]


@pytest.mark.parametrize(
    "caso",
    [
        {"redirect_uri": REDIRECT_QUERY, "state": STATE_RESERVADO},
        {"redirect_uri": REDIRECT_PLAIN, "state": STATE_RESERVADO, "response_type": "token"},
    ],
    ids=["codigo", "response_type_invalido"],
)
def test_authorize_url_devuelve_la_misma_forma_que_authorize(client, app_ctx, caso):
    """La variante JSON que consume la SPA no puede divergir del redirect: es la
    misma URL, y hasta ahora cada una la armaba por su cuenta."""
    location = _authorize(client, app_ctx, app_ctx["token"], **caso)
    json_url = _authorize_url(client, app_ctx, app_ctx["token"], **caso)

    assert _sin_query(json_url) == _sin_query(location)
    # El `code` es de un solo uso, así que se compara todo lo demás.
    assert {k: v for k, v in _query(json_url).items() if k != "code"} == {
        k: v for k, v in _query(location).items() if k != "code"
    }


def test_authorize_url_tambien_rechaza_response_type_no_soportado(client, app_ctx):
    json_url = _authorize_url(
        client, app_ctx, app_ctx["token"], redirect_uri=REDIRECT_QUERY, state="s", response_type="token"
    )

    params = _query(json_url)
    assert params["error"] == ["unsupported_response_type"]
    assert params["tenant"] == ["jal"]
    assert _codes_emitidos() == 0
