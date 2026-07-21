"""Carrera real de rotación de refresh a través del endpoint /auth/token (issue #38).

SQLite no reproduce el lock de fila que produce el bloqueo real: dos requests
concurrentes del mismo refresh_token, atravesando el endpoint completo (incluida la
pausa entre el blacklisteo en Redis y el commit), ejercen la contención tal como
ocurriría en producción. Requiere un PostgreSQL real y EXCLUSIVO de pruebas: exporta
MINERVA_TEST_POSTGRES_URL apuntando a una base cuyo nombre termine en `_test`
(ver tests.conftest.require_test_database_url), o el test se salta.
"""

import asyncio
import os
import threading

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.database import get_session
from app.core.dependencies.db import get_db
from app.core.models import import_models
from app.core.redis import get_redis
from app.core.security import hash_secret, hash_token
from app.core.token_blacklist import is_revoked
from app.main import app
from app.modules.applications.models import Application, RedirectURI
from app.modules.auth import router as auth_router
from app.modules.auth.models import RefreshToken
from app.modules.auth.repository import RefreshTokenRepository
from app.modules.auth.service import AuthService
from app.modules.groups.models import UserRole
from app.modules.oidc.service import OIDCService
from app.modules.roles.models import Role
from app.modules.users.models import User
from tests.conftest import require_test_database_url

PG_URL = os.environ.get("MINERVA_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(
    not PG_URL,
    reason="requiere MINERVA_TEST_POSTGRES_URL apuntando a un PostgreSQL real (SQLite no reproduce el lock de fila)",
)

CLIENT_SECRET = "secret-race-pg-test"
REDIRECT_URI = "https://cliente.example.com/cb"


@pytest.fixture
def pg_engine():
    """Function-scoped (no module): varios tests de este archivo insertan filas con
    slugs/emails fijos vía `ctx`, así que cada test necesita un esquema limpio propio
    en vez de acumular estado sobre el mismo engine compartido."""
    require_test_database_url(PG_URL)
    import_models()
    engine = create_engine(PG_URL, echo=False)
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    yield engine
    SQLModel.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def pg_client(pg_engine):
    """TestClient contra el endpoint real, con la sesión de DB apuntando a
    PostgreSQL en vez de al engine SQLite que conftest.py registra globalmente.
    Restaura los overrides originales al terminar para no afectar otros tests."""

    def override_db():
        with Session(pg_engine) as session:
            yield session

    prev_db = app.dependency_overrides.get(get_db)
    prev_session = app.dependency_overrides.get(get_session)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_session] = override_db
    try:
        yield TestClient(app)
    finally:
        if prev_db is not None:
            app.dependency_overrides[get_db] = prev_db
        else:
            app.dependency_overrides.pop(get_db, None)
        if prev_session is not None:
            app.dependency_overrides[get_session] = prev_session
        else:
            app.dependency_overrides.pop(get_session, None)


def _grant_role(session: Session, application_id: str, user_id: str) -> None:
    """Variante de `tests.conftest.grant_role` con flush explícito entre inserts.

    Sin `Relationship()` declarada, SQLAlchemy no infiere el orden de inserción
    entre tablas por la sola presencia de un `foreign_key`; SQLite lo tolera porque
    no aplica FKs por defecto, pero PostgreSQL sí, así que aquí hace falta ser
    explícitos con el orden real de escritura."""
    role = Role(application_id=application_id, name="Member", slug="member")
    session.add(role)
    session.flush()
    session.add(UserRole(user_id=user_id, role_id=role.id))
    session.flush()


@pytest.fixture
def ctx(pg_engine, pg_client):
    with Session(pg_engine) as session:
        app_row = Application(
            name="Race App", slug="race-app-endpoint", client_secret_hash=hash_secret(CLIENT_SECRET), status="active"
        )
        session.add(app_row)
        session.flush()
        session.add(RedirectURI(application_id=app_row.id, uri=REDIRECT_URI, environment="production"))
        user = User(
            email="race-endpoint@iieg.gob.mx", full_name="Race Endpoint", auth_provider="local", status="active"
        )
        session.add(user)
        session.flush()
        _grant_role(session, app_row.id, user.id)
        session.commit()
        session.refresh(app_row)
        session.refresh(user)
        OIDCService(session).ensure_active_signing_key()
        client_id, user_id = app_row.client_id, user.id

    with Session(pg_engine) as session:
        url, _ = AuthService(session).authorize(client_id, REDIRECT_URI, user_id, "s", "openid")
    code = url.split("code=")[1].split("&")[0]

    exchange = pg_client.post(
        "/auth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": CLIENT_SECRET,
            "code": code,
            "redirect_uri": REDIRECT_URI,
        },
    )
    assert exchange.status_code == 200, exchange.text

    return {"client_id": client_id, "user_id": user_id, "raw_refresh": exchange.json()["refresh_token"]}


def _start_paused_rotation(pg_client, ctx, monkeypatch, results, label="winner"):
    """Arranca en un hilo aparte una rotación real de /auth/token y la detiene justo
    antes del commit, pausando (con un Event, sin sleeps) el paso de blacklisteo en
    Redis del router. Deja el lock de fila (FOR UPDATE NOWAIT) abierto el tiempo que
    el caller necesite para ejercer contención real contra otro request/flujo.
    Devuelve (hilo, release_gate); el caller decide cuándo liberar el gate."""
    reached_pause = threading.Event()
    release_gate = threading.Event()
    real_revoke_jti = auth_router.revoke_jti

    async def paused_revoke_jti(redis, jti, ttl):
        reached_pause.set()
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, release_gate.wait)
        await real_revoke_jti(redis, jti, ttl)

    monkeypatch.setattr(auth_router, "revoke_jti", paused_revoke_jti)

    def call_refresh() -> None:
        results[label] = pg_client.post(
            "/auth/token",
            data={
                "grant_type": "refresh_token",
                "client_id": ctx["client_id"],
                "client_secret": CLIENT_SECRET,
                "refresh_token": ctx["raw_refresh"],
            },
        )

    thread = threading.Thread(target=call_refresh)
    thread.start()
    assert reached_pause.wait(timeout=10), "la rotación no llegó al punto de pausa Redis→commit"
    return thread, release_gate


def _make_admin(pg_engine, application_id: str) -> str:
    """Crea un admin de Minerva en la base de pruebas y devuelve su token de sesión
    (Bearer, `typ=session`) — el mismo mecanismo que `tests.conftest._mint_session_token`
    pero contra el engine de PostgreSQL en vez del `test_engine` de SQLite."""
    with Session(pg_engine) as session:
        admin_user = User(
            email="race-admin@iieg.gob.mx", full_name="Race Admin", auth_provider="local", status="active"
        )
        session.add(admin_user)
        session.flush()
        admin_role = Role(application_id=application_id, name="Admin", slug="minerva.admin")
        session.add(admin_role)
        session.flush()
        session.add(UserRole(user_id=admin_user.id, role_id=admin_role.id))
        session.commit()
        session.refresh(admin_user)
        return OIDCService(session).issue_session_token(admin_user.id, admin_user.email, admin_user.full_name)


async def test_endpoint_race_ganador_valido_perdedor_rechazado_sin_bloqueo(pg_engine, pg_client, ctx, monkeypatch):
    """Dos requests concurrentes a /auth/token (grant_type=refresh_token) con el
    mismo refresh_token, ejerciendo la pausa real Redis→commit del router.

    Se retrasa el paso de blacklisteo en Redis del ganador (con un Event, no un
    sleep) para mantener su transacción abierta el tiempo suficiente; el perdedor
    debe fallar rápido contra el `FOR UPDATE NOWAIT` de PostgreSQL sin que nadie
    libere el lock manualmente desde otro hilo. Cada request abre, confirma/revierte
    y cierra su propia Session (la maneja el endpoint real vía DI, no el test)."""
    results: dict[str, object] = {}
    winner_thread, release_gate = _start_paused_rotation(pg_client, ctx, monkeypatch, results)

    # El ganador ya tiene el lock de fila (FOR UPDATE NOWAIT) y está detenido en el
    # paso Redis→commit. El perdedor debe resolverse solo, sin ayuda del test.
    def call_loser() -> None:
        results["loser"] = pg_client.post(
            "/auth/token",
            data={
                "grant_type": "refresh_token",
                "client_id": ctx["client_id"],
                "client_secret": CLIENT_SECRET,
                "refresh_token": ctx["raw_refresh"],
            },
        )

    loser_thread = threading.Thread(target=call_loser)
    loser_thread.start()
    loser_thread.join(timeout=10)
    assert not loser_thread.is_alive(), "el perdedor no debió bloquearse esperando el lock (se esperaba NOWAIT)"

    loser_response = results["loser"]
    assert loser_response.status_code == 409, loser_response.text

    release_gate.set()
    winner_thread.join(timeout=10)
    assert not winner_thread.is_alive(), "deadlock: el ganador nunca terminó"

    winner_response = results["winner"]
    assert winner_response.status_code == 200, winner_response.text
    winner_body = winner_response.json()

    with Session(pg_engine) as session:
        repo = RefreshTokenRepository(session)
        original = repo.get_by_hash(hash_token(ctx["raw_refresh"]))
        winner_row = repo.get_by_hash(hash_token(winner_body["refresh_token"]))

        family_members = list(session.exec(select(RefreshToken).where(RefreshToken.family_id == original.family_id)))
        assert len(family_members) == 2, "el canje concurrente no debe crear mas de un sucesor"
        assert original.status == "rotated"
        assert winner_row is not None
        # A diferencia de un reúso genuino, la contención concurrente NO revoca la
        # familia: el sucesor del ganador sigue activo y utilizable.
        assert winner_row.status == "active"

    winner_jti = jwt.get_unverified_claims(winner_body["access_token"])["jti"]
    fake_redis = app.dependency_overrides[get_redis]()
    assert not await is_revoked(fake_redis, winner_jti), "el access token del ganador no debe quedar blacklisteado"

    # --- Reúso posterior, ya terminada la carrera: el original (ya rotado) se
    # presenta de nuevo. Esto SÍ es reúso genuino (no contención), así que la
    # política existente de revocar toda la familia se mantiene, incluido el
    # sucesor que el ganador acaba de recibir.
    reuse_response = pg_client.post(
        "/auth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": ctx["client_id"],
            "client_secret": CLIENT_SECRET,
            "refresh_token": ctx["raw_refresh"],
        },
    )
    assert reuse_response.status_code == 400, reuse_response.text

    with Session(pg_engine) as session:
        repo = RefreshTokenRepository(session)
        original_after_reuse = repo.get_by_hash(hash_token(ctx["raw_refresh"]))
        winner_after_reuse = repo.get_by_hash(hash_token(winner_body["refresh_token"]))
        assert original_after_reuse.status == "revoked"
        assert winner_after_reuse.status == "revoked"


def test_endpoint_revoke_concurrente_con_rotacion_en_curso(pg_engine, pg_client, ctx, monkeypatch):
    """POST /auth/revoke contra el mismo refresh token que se está rotando ahora
    mismo (revoke_family hace FOR UPDATE NOWAIT sobre toda la familia) no debe
    bloquearse esperando el lock: falla rápido con conflicto, no persiste una
    revocación parcial, y funciona con normalidad una vez termina la rotación."""
    results: dict[str, object] = {}
    winner_thread, release_gate = _start_paused_rotation(pg_client, ctx, monkeypatch, results)

    def call_revoke() -> None:
        results["revoke"] = pg_client.post(
            "/auth/revoke",
            data={"client_id": ctx["client_id"], "client_secret": CLIENT_SECRET, "token": ctx["raw_refresh"]},
        )

    revoke_thread = threading.Thread(target=call_revoke)
    revoke_thread.start()
    revoke_thread.join(timeout=10)
    assert not revoke_thread.is_alive(), "el revoke no debió bloquearse esperando el lock (se esperaba NOWAIT)"
    assert results["revoke"].status_code == 409, results["revoke"].text

    release_gate.set()
    winner_thread.join(timeout=10)
    assert not winner_thread.is_alive(), "deadlock: la rotación nunca terminó"
    assert results["winner"].status_code == 200, results["winner"].text
    winner_body = results["winner"].json()

    # Nada quedó parcialmente revocado por el intento fallido de /auth/revoke: el
    # sucesor de la rotación sigue activo.
    with Session(pg_engine) as session:
        repo = RefreshTokenRepository(session)
        winner_row = repo.get_by_hash(hash_token(winner_body["refresh_token"]))
        assert winner_row.status == "active"

    # Ya terminada la rotación (sin contención), reintentar la revocación funciona.
    retry = pg_client.post(
        "/auth/revoke",
        data={
            "client_id": ctx["client_id"],
            "client_secret": CLIENT_SECRET,
            "token": winner_body["refresh_token"],
        },
    )
    assert retry.status_code == 200, retry.text
    with Session(pg_engine) as session:
        repo = RefreshTokenRepository(session)
        winner_row_after = repo.get_by_hash(hash_token(winner_body["refresh_token"]))
        assert winner_row_after.status == "revoked"


def test_endpoint_desactivar_usuario_concurrente_con_rotacion_en_curso(pg_engine, pg_client, ctx, monkeypatch):
    """PATCH /users/{id}/status para desactivar al dueño del refresh token que se
    está rotando ahora mismo (revoke_all_for_user hace FOR UPDATE NOWAIT) no debe
    bloquearse ni dejar el status del usuario parcialmente persistido si falla por
    contención; debe funcionar con normalidad una vez termina la rotación."""
    with Session(pg_engine) as session:
        app_id = session.exec(select(Application).where(Application.client_id == ctx["client_id"])).first().id
    admin_token = _make_admin(pg_engine, application_id=app_id)

    results: dict[str, object] = {}
    winner_thread, release_gate = _start_paused_rotation(pg_client, ctx, monkeypatch, results)

    def call_deactivate() -> None:
        results["deactivate"] = pg_client.patch(
            f"/users/{ctx['user_id']}/status",
            json={"status": "inactive"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )

    deactivate_thread = threading.Thread(target=call_deactivate)
    deactivate_thread.start()
    deactivate_thread.join(timeout=10)
    assert not deactivate_thread.is_alive(), "la desactivación no debió bloquearse esperando el lock (NOWAIT)"
    assert results["deactivate"].status_code == 409, results["deactivate"].text

    release_gate.set()
    winner_thread.join(timeout=10)
    assert not winner_thread.is_alive(), "deadlock: la rotación nunca terminó"
    assert results["winner"].status_code == 200, results["winner"].text

    # Nada quedó parcialmente persistido: el intento fallido no dejó al usuario a
    # medio desactivar (el router revierte toda la transacción ante el conflicto).
    with Session(pg_engine) as session:
        user = session.get(User, ctx["user_id"])
        assert user.status == "active"

    # Ya terminada la rotación (sin contención), reintentar la desactivación funciona.
    retry = pg_client.patch(
        f"/users/{ctx['user_id']}/status",
        json={"status": "inactive"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert retry.status_code == 200, retry.text
    with Session(pg_engine) as session:
        user_after = session.get(User, ctx["user_id"])
        assert user_after.status == "inactive"
