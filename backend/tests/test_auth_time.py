"""`auth_time` es el instante de autenticación **de cada sesión**, no del usuario.

Antes se fijaba a `now` al crear el código, así que un SSO silencioso reportaba una
frescura falsa. Tomarlo de `user.last_login_at` tampoco sirve: ese valor es global por
usuario, así que iniciar sesión en otro navegador rejuvenecería esta sesión y le dejaría
pasar un `max_age` que ya no cumple. Por eso viaja dentro del token `typ=session`.
"""

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlmodel import Session, select

from app.core.security import decode_token_rs256, hash_secret
from app.modules.applications.models import Application, RedirectURI
from app.modules.auth.service import AuthService
from app.modules.oidc.service import OIDCService
from app.modules.users.models import User
from tests.conftest import grant_role, test_engine

CLIENT_SECRET = "auth-time-secret"
REDIRECT_URI = "https://authtime.example.com/callback"
EMAIL = "authtime@iieg.gob.mx"
PASSWORD = "authtime-pass-123"


@pytest.fixture
def app_ctx(client):
    # Se registra por HTTP para que el usuario quede con contraseña utilizable en
    # /auth/login (varios casos necesitan un login real, no un token acuñado).
    resp = client.post("/auth/register", json={"email": EMAIL, "full_name": "Auth Time", "password": PASSWORD})
    assert resp.status_code == 201, resp.text
    client.cookies.clear()

    with Session(test_engine) as session:
        app_row = Application(
            name="Auth Time App",
            slug="auth-time-app",
            client_secret_hash=hash_secret(CLIENT_SECRET),
            status="active",
        )
        session.add(app_row)
        session.flush()
        session.add(RedirectURI(application_id=app_row.id, uri=REDIRECT_URI, environment="production"))
        user = session.exec(select(User).where(User.email == EMAIL)).first()
        grant_role(session, app_row.id, user.id)
        session.commit()
        session.refresh(app_row)
        OIDCService(session).ensure_active_signing_key()
        return {"client_id": app_row.client_id, "user_id": user.id}


def _jwks() -> dict:
    with Session(test_engine) as session:
        return OIDCService(session).build_jwks()


def _sesion(ctx: dict, autenticada_hace: timedelta = timedelta(0)) -> str:
    """Token de una sesión de panel que se autenticó en un momento dado."""
    momento = int((datetime.now(timezone.utc) - autenticada_hace).timestamp())
    with Session(test_engine) as session:
        return OIDCService(session).issue_session_token(ctx["user_id"], EMAIL, "Auth Time", auth_time=momento)


def _claims_sesion(token: str) -> dict:
    return decode_token_rs256(token, _jwks(), audience="minerva")


def _authorize(client, ctx: dict, token: str, **params):
    return client.get(
        "/auth/authorize",
        params={
            "client_id": ctx["client_id"],
            "redirect_uri": REDIRECT_URI,
            "state": "s",
            "scope": "openid",
            **params,
        },
        headers={"Authorization": f"Bearer {token}"},
        follow_redirects=False,
    )


def _id_token_claims(client, ctx: dict, token: str, **params) -> dict:
    """Recorrido completo: /authorize emite el código y /token entrega el id_token."""
    resp = _authorize(client, ctx, token, **params)
    assert resp.status_code in (302, 307), resp.text
    query = parse_qs(urlsplit(resp.headers["location"]).query)
    assert "code" in query, f"esperaba un código, llegó {query}"

    canje = client.post(
        "/auth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": ctx["client_id"],
            "client_secret": CLIENT_SECRET,
            "code": query["code"][0],
            "redirect_uri": REDIRECT_URI,
        },
    )
    assert canje.status_code == 200, canje.text
    return decode_token_rs256(canje.json()["id_token"], _jwks(), audience=ctx["client_id"])


def test_auth_time_es_la_autenticacion_real_no_el_instante_del_codigo(client, app_ctx):
    """Regresión directa: con la sesión autenticada 6 h atrás, el id_token debe
    reportar esas 6 h, no el momento en que se pidió el código."""
    token = _sesion(app_ctx, autenticada_hace=timedelta(hours=6))

    claims = _id_token_claims(client, app_ctx, token)

    assert claims["auth_time"] == _claims_sesion(token)["auth_time"]
    antiguedad = datetime.now(timezone.utc).timestamp() - claims["auth_time"]
    assert antiguedad > 5.5 * 3600, "auth_time se está fijando al instante del código"


def test_sso_repetido_no_refresca_auth_time(client, app_ctx):
    """Dos autorizaciones con la misma sesión: la autenticación es la misma, así que
    el valor reportado no puede moverse."""
    token = _sesion(app_ctx, autenticada_hace=timedelta(hours=6))

    primera = _id_token_claims(client, app_ctx, token)
    segunda = _id_token_claims(client, app_ctx, token)

    assert primera["auth_time"] == segunda["auth_time"]


def test_iniciar_sesion_en_otro_navegador_no_rejuvenece_esta_sesion(client, app_ctx):
    """El caso que un `auth_time` global por usuario resolvía mal.

    La sesión A se autenticó hace 6 h. El mismo usuario inicia sesión en otro navegador
    (sesión B, fresca). A no debe verse afectada: ni en lo que reporta ni en lo que se
    le exige — si `max_age` mirara el último login del usuario, A pasaría un `max_age`
    de 1 h que en realidad no cumple."""
    sesion_a = _sesion(app_ctx, autenticada_hace=timedelta(hours=6))
    antes = _id_token_claims(client, app_ctx, sesion_a)["auth_time"]

    login_b = client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert login_b.status_code == 200, login_b.text
    client.cookies.clear()

    assert _id_token_claims(client, app_ctx, sesion_a)["auth_time"] == antes
    # Y sigue sin acreditar frescura: A no se autenticó, se autenticó B.
    resp = _authorize(client, app_ctx, sesion_a, max_age=3600)
    assert "/login?next=" in resp.headers["location"], "el login del otro navegador rejuveneció esta sesión"


def test_una_sesion_nueva_si_trae_auth_time_fresco(client, app_ctx):
    reciente = _sesion(app_ctx)
    vieja = _sesion(app_ctx, autenticada_hace=timedelta(hours=6))

    fresco = _id_token_claims(client, app_ctx, reciente)["auth_time"]

    assert fresco > _id_token_claims(client, app_ctx, vieja)["auth_time"]
    assert datetime.now(timezone.utc).timestamp() - fresco < 60


def test_refrescar_el_token_no_cuenta_como_reautenticacion(client, app_ctx):
    """`/auth/refresh` alarga la sesión, no vuelve a autenticar. Si renovara el
    `auth_time`, un `max_age` nunca se cumpliría en una sesión que se refresca sola."""
    token = _sesion(app_ctx, autenticada_hace=timedelta(hours=6))
    original = _claims_sesion(token)["auth_time"]

    with Session(test_engine) as session:
        reemitido = AuthService(session).reissue_session_token(_claims_sesion(token))["access_token"]

    assert _claims_sesion(reemitido)["auth_time"] == original


def test_auth_time_reportado_es_coherente_con_lo_que_exige_max_age(client, app_ctx):
    """Lo que Minerva enforcea y lo que reporta salen del mismo valor: un `max_age`
    más corto que la antigüedad de la sesión exige re-autenticar, y uno más largo pasa
    reportando exactamente esa antigüedad."""
    token = _sesion(app_ctx, autenticada_hace=timedelta(hours=6))
    esperado = _claims_sesion(token)["auth_time"]

    resp = _authorize(client, app_ctx, token, max_age=3600)
    assert "/login?next=" in resp.headers["location"]

    claims = _id_token_claims(client, app_ctx, token, max_age=10 * 3600)
    assert claims["auth_time"] == esperado


def _sesion_legacy(ctx: dict) -> str:
    """Token de sesión como los que se emitían antes del claim `auth_time`. Su `iat` es
    de ahora mismo, igual que el de una sesión vieja recién refrescada."""
    from app.core.security import create_access_token_rs256

    with Session(test_engine) as session:
        kid, pem = OIDCService(session).get_active_private_pem()
        return create_access_token_rs256(
            user_id=ctx["user_id"],
            email=EMAIL,
            name="Auth Time",
            kid=kid,
            private_key_pem=pem,
            application_slug="minerva",
            typ="session",
        )


def test_un_token_legacy_con_iat_reciente_no_satisface_max_age(client, app_ctx):
    """`iat` NO es prueba de autenticación: antes de este cambio `/auth/refresh` lo
    regeneraba sin re-autenticar a nadie, así que una sesión de hace días recién
    refrescada exhibiría un `iat` de hace segundos. Sin `auth_time` no hay evidencia,
    y sin evidencia se re-autentica por más fresco que luzca el token."""
    legacy = _sesion_legacy(app_ctx)
    claims = _claims_sesion(legacy)
    assert "auth_time" not in claims
    assert datetime.now(timezone.utc).timestamp() - claims["iat"] < 60, "el iat es reciente a propósito"

    resp = _authorize(client, app_ctx, legacy, max_age=3600)

    assert "/login?next=" in resp.headers["location"], "el iat se está aceptando como auth_time"


def test_un_token_legacy_no_se_puede_refrescar(client, app_ctx):
    """El refresh convertiría ese `iat` en un `auth_time` con apariencia legítima, que
    ya nadie podría distinguir de una autenticación real. Se corta ahí: un re-login."""
    legacy = _sesion_legacy(app_ctx)

    resp = client.post("/auth/refresh", headers={"Authorization": f"Bearer {legacy}"})

    assert resp.status_code == 401, resp.text


def test_un_token_legacy_sigue_sirviendo_para_sso_sin_max_age(client, app_ctx):
    """La exigencia es proporcional: sin `max_age` el consumidor no pidió frescura, así
    que la sesión sigue valiendo — solo que su id_token omite `auth_time`, en vez de
    inventar uno. El claim únicamente es obligatorio cuando se pidió `max_age`."""
    claims = _id_token_claims(client, app_ctx, _sesion_legacy(app_ctx))

    assert "auth_time" not in claims
