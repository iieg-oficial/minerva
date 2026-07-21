"""`auth_time` del id_token debe ser el instante de la autenticación real, no el de la
emisión del código.

Antes se fijaba a `now` al crear el código, así que un SSO silencioso reportaba una
frescura falsa y —peor— Minerva se contradecía: `_requires_reauth` evalúa `max_age`
contra `user.last_login_at`, o sea enforceaba contra un valor y reportaba otro.
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
from app.shared.datetime_utils import as_utc
from tests.conftest import grant_role, test_engine

CLIENT_SECRET = "auth-time-secret"
REDIRECT_URI = "https://authtime.example.com/callback"
EMAIL = "authtime@iieg.gob.mx"
PASSWORD = "authtime-pass-123"


@pytest.fixture
def app_ctx(client):
    # Se registra por HTTP para que el usuario quede con contraseña utilizable en
    # /auth/login (uno de los casos comprueba que un login real sí mueve auth_time).
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


def _last_login() -> datetime | None:
    with Session(test_engine) as session:
        user = session.exec(select(User).where(User.email == EMAIL)).first()
        return as_utc(user.last_login_at) if user.last_login_at else None


def _set_last_login(hace: timedelta) -> datetime:
    """Mueve el último login al pasado, simulando una sesión que ya lleva rato abierta."""
    momento = datetime.now(timezone.utc) - hace
    with Session(test_engine) as session:
        user = session.exec(select(User).where(User.email == EMAIL)).first()
        user.last_login_at = momento
        session.add(user)
        session.commit()
    return momento


def _authorize(ctx: dict, **kwargs) -> tuple[str | None, str | None]:
    with Session(test_engine) as session:
        return AuthService(session).authorize(ctx["client_id"], REDIRECT_URI, ctx["user_id"], "s", "openid", **kwargs)


def _id_token_claims(client, ctx: dict, **kwargs) -> dict:
    """Recorrido completo: /authorize emite el código y /token entrega el id_token."""
    url, reason = _authorize(ctx, **kwargs)
    assert reason is None, f"no debía pedir re-autenticación: {reason}"
    code = parse_qs(urlsplit(url).query)["code"][0]

    resp = client.post(
        "/auth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": ctx["client_id"],
            "client_secret": CLIENT_SECRET,
            "code": code,
            "redirect_uri": REDIRECT_URI,
        },
    )
    assert resp.status_code == 200, resp.text
    return decode_token_rs256(resp.json()["id_token"], _jwks(), audience=ctx["client_id"])


def test_auth_time_es_el_login_real_no_el_instante_del_codigo(client, app_ctx):
    """Regresión directa: con el login 6 h atrás, el id_token debe reportar esas 6 h."""
    momento = _set_last_login(timedelta(hours=6))

    claims = _id_token_claims(client, app_ctx)

    assert claims["auth_time"] == int(momento.timestamp())
    antiguedad = datetime.now(timezone.utc).timestamp() - claims["auth_time"]
    assert antiguedad > 5.5 * 3600, "auth_time se está fijando al instante del código"


def test_sso_repetido_no_refresca_auth_time(client, app_ctx):
    """Dos autorizaciones seguidas sin login nuevo: la autenticación es la misma, así
    que el valor reportado no puede moverse."""
    _set_last_login(timedelta(hours=6))

    primera = _id_token_claims(client, app_ctx)
    segunda = _id_token_claims(client, app_ctx)

    assert primera["auth_time"] == segunda["auth_time"]


def test_un_login_real_si_mueve_auth_time(client, app_ctx):
    _set_last_login(timedelta(hours=6))
    antes = _id_token_claims(client, app_ctx)["auth_time"]

    resp = client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert resp.status_code == 200, resp.text
    client.cookies.clear()

    despues = _id_token_claims(client, app_ctx)["auth_time"]
    assert despues > antes
    assert datetime.now(timezone.utc).timestamp() - despues < 60


def test_el_registro_marca_el_ultimo_login(client, app_ctx):
    """El alta deja sesión abierta, así que es un evento de autenticación: sin esto un
    recién registrado no podría reportar `auth_time` ni pasar ningún `max_age`."""
    assert _last_login() is not None


def test_auth_time_reportado_es_coherente_con_lo_que_exige_max_age(client, app_ctx):
    """Lo que Minerva enforcea y lo que reporta salen de la misma fuente: un `max_age`
    más corto que la antigüedad del login exige re-autenticar, y uno más largo pasa
    reportando exactamente esa antigüedad."""
    momento = _set_last_login(timedelta(hours=6))

    url, reason = _authorize(app_ctx, max_age=3600)
    assert url is None
    assert reason == "max_age"

    claims = _id_token_claims(client, app_ctx, max_age=10 * 3600)
    assert claims["auth_time"] == int(momento.timestamp())
