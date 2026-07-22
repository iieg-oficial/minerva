"""Atomicidad y revalidación en el canje de código/refresh (issue #38)."""

import pytest
from sqlmodel import Session, select

from app.core.exceptions import ForbiddenError
from app.core.security import hash_secret, hash_token
from app.modules.applications.models import Application, RedirectURI
from app.modules.auth.repository import RefreshTokenRepository
from app.modules.auth.service import AuthService, RefreshReuseError
from app.modules.oidc.service import OIDCService
from app.modules.users.models import User
from tests.conftest import grant_role, test_engine

CLIENT_SECRET = "secret-atomicity-test"
REDIRECT_URI = "https://cliente.example.com/cb"


@pytest.fixture
def app_ctx():
    with Session(test_engine) as session:
        app_row = Application(
            name="Atomicity App",
            slug="atomicity-app",
            client_secret_hash=hash_secret(CLIENT_SECRET),
            status="active",
        )
        session.add(app_row)
        session.flush()
        session.add(RedirectURI(application_id=app_row.id, uri=REDIRECT_URI, environment="production"))
        user = User(email="atomicity@iieg.gob.mx", full_name="Atomicity User", status="active")
        session.add(user)
        grant_role(session, app_row.id, user.id)
        session.commit()
        session.refresh(app_row)
        session.refresh(user)
        OIDCService(session).ensure_active_signing_key()
        return {"client_id": app_row.client_id, "user_id": user.id}


def _issue_code(ctx: dict) -> str:
    with Session(test_engine) as session:
        url, _ = AuthService(session).authorize(ctx["client_id"], REDIRECT_URI, ctx["user_id"], "s", "openid")
    return url.split("code=")[1].split("&")[0]


def _set_app_status(client_id: str, status: str) -> None:
    with Session(test_engine) as session:
        app_row = session.exec(select(Application).where(Application.client_id == client_id)).first()
        app_row.status = status
        session.add(app_row)
        session.commit()


def _set_user_status(user_id: str, status: str) -> None:
    with Session(test_engine) as session:
        user = session.exec(select(User).where(User.id == user_id)).first()
        user.status = status
        session.add(user)
        session.commit()


def test_codigo_concurrente_un_solo_ganador(app_ctx):
    """Dos sesiones leen el mismo auth_code activo (la lectura sucia del bug);
    solo una debe poder reclamarlo."""
    code = _issue_code(app_ctx)

    with Session(test_engine) as session_a, Session(test_engine) as session_b:
        service_a = AuthService(session_a)
        service_b = AuthService(session_b)

        auth_code_a = service_a.auth_code_repo.get_by_code(code)
        auth_code_b = service_b.auth_code_repo.get_by_code(code)
        assert auth_code_a is not None and auth_code_b is not None

        assert service_a.auth_code_repo.mark_used(auth_code_a) is True
        assert service_b.auth_code_repo.mark_used(auth_code_b) is False

    with Session(test_engine) as session:
        assert AuthService(session).auth_code_repo.get_by_code(code) is None


def test_refresh_concurrente_un_solo_ganador(app_ctx):
    code = _issue_code(app_ctx)
    with Session(test_engine) as session:
        tokens = AuthService(session).exchange_token(
            app_ctx["client_id"], code, REDIRECT_URI, client_secret=CLIENT_SECRET
        )
    raw_refresh = tokens["refresh_token"]

    with Session(test_engine) as session_a, Session(test_engine) as session_b:
        refresh_a = RefreshTokenRepository(session_a).get_by_hash(hash_token(raw_refresh))
        refresh_b = RefreshTokenRepository(session_b).get_by_hash(hash_token(raw_refresh))

        assert RefreshTokenRepository(session_a).mark_rotated(refresh_a) is True
        assert RefreshTokenRepository(session_b).mark_rotated(refresh_b) is False

    # El perdedor, si siguiera el flujo completo, cae en la rama de reúso (familia revocada).
    with Session(test_engine) as session:
        with pytest.raises(RefreshReuseError):
            AuthService(session).rotate_refresh_token(app_ctx["client_id"], raw_refresh, client_secret=CLIENT_SECRET)


def test_canje_rechaza_app_inactiva(app_ctx):
    code = _issue_code(app_ctx)
    _set_app_status(app_ctx["client_id"], "inactive")

    with Session(test_engine) as session:
        with pytest.raises(ForbiddenError):
            AuthService(session).exchange_token(app_ctx["client_id"], code, REDIRECT_URI, client_secret=CLIENT_SECRET)

    # El código sigue sin usarse: la app inactiva se rechaza antes del reclamo.
    with Session(test_engine) as session:
        assert AuthService(session).auth_code_repo.get_by_code(code) is not None


def test_canje_rechaza_usuario_inactivo(app_ctx):
    code = _issue_code(app_ctx)
    _set_user_status(app_ctx["user_id"], "inactive")

    with Session(test_engine) as session:
        with pytest.raises(ForbiddenError):
            AuthService(session).exchange_token(app_ctx["client_id"], code, REDIRECT_URI, client_secret=CLIENT_SECRET)

    with Session(test_engine) as session:
        assert AuthService(session).auth_code_repo.get_by_code(code) is not None


def test_refresh_rechaza_app_inactiva(app_ctx):
    code = _issue_code(app_ctx)
    with Session(test_engine) as session:
        tokens = AuthService(session).exchange_token(
            app_ctx["client_id"], code, REDIRECT_URI, client_secret=CLIENT_SECRET
        )
    raw_refresh = tokens["refresh_token"]

    _set_app_status(app_ctx["client_id"], "inactive")

    with Session(test_engine) as session:
        with pytest.raises(ForbiddenError):
            AuthService(session).rotate_refresh_token(app_ctx["client_id"], raw_refresh, client_secret=CLIENT_SECRET)
