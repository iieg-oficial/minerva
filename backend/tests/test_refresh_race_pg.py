"""Carrera real de rotación de refresh contra PostgreSQL (issue #38).

SQLite no reproduce el lock de fila que produce el bloqueo real: dos hilos con
conexiones/sesiones independientes ejercen la contención tal como ocurriría en
producción (dos requests concurrentes del mismo refresh_token). Requiere un
PostgreSQL real: exporta MINERVA_TEST_POSTGRES_URL (p. ej. levantando
`docker compose up -d postgres` y usando el puerto mapeado en .env) o el test
se salta.
"""

import os
import queue
import threading

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.models import import_models
from app.core.security import hash_secret, hash_token
from app.modules.applications.models import Application, RedirectURI
from app.modules.auth.models import RefreshToken
from app.modules.auth.repository import RefreshTokenRepository
from app.modules.auth.service import AuthService, RefreshReuseError
from app.modules.groups.models import UserRole
from app.modules.oidc.service import OIDCService
from app.modules.roles.models import Role
from app.modules.users.models import User

PG_URL = os.environ.get("MINERVA_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(
    not PG_URL,
    reason="requiere MINERVA_TEST_POSTGRES_URL apuntando a un PostgreSQL real (SQLite no reproduce el lock de fila)",
)

CLIENT_SECRET = "secret-race-pg-test"
REDIRECT_URI = "https://cliente.example.com/cb"


@pytest.fixture(scope="module")
def pg_engine():
    import_models()
    engine = create_engine(PG_URL, echo=False)
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    yield engine
    SQLModel.metadata.drop_all(engine)
    engine.dispose()


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
def ctx(pg_engine):
    with Session(pg_engine) as session:
        app_row = Application(
            name="Race App", slug="race-app-pg", client_secret_hash=hash_secret(CLIENT_SECRET), status="active"
        )
        session.add(app_row)
        session.flush()
        session.add(RedirectURI(application_id=app_row.id, uri=REDIRECT_URI, environment="production"))
        user = User(email="race@iieg.gob.mx", full_name="Race User", auth_provider="local", status="active")
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

    with Session(pg_engine) as session:
        tokens = AuthService(session).exchange_token(client_id, code, REDIRECT_URI, client_secret=CLIENT_SECRET)

    return {"client_id": client_id, "raw_refresh": tokens["refresh_token"]}


def test_rotacion_concurrente_real_un_solo_ganador(pg_engine, ctx):
    """Dos hilos con sesiones/conexiones propias rotan el mismo refresh token a la vez.

    El perdedor se bloquea dentro del UPDATE condicional (lock de fila de PostgreSQL)
    hasta que el ganador comitea; el harness mantiene esa transacción ganadora abierta
    a propósito (no comitea hasta confirmar, vía la cola, que ya resolvió) para ejercer
    la contención real, igual que ocurre en el endpoint entre el reclamo y el await a
    Redis (issue #38, punto 1).
    """
    barrier = threading.Barrier(2)
    results: queue.Queue = queue.Queue()

    def worker(label: str):
        session = Session(pg_engine)
        service = AuthService(session)
        barrier.wait()
        try:
            response, jtis = service.rotate_refresh_token(
                ctx["client_id"], ctx["raw_refresh"], client_secret=CLIENT_SECRET, commit=False
            )
            results.put((label, "success", response, jtis, session))
        except RefreshReuseError as exc:
            results.put((label, "reuse", exc, None, session))

    thread_a = threading.Thread(target=worker, args=("a",))
    thread_b = threading.Thread(target=worker, args=("b",))
    thread_a.start()
    thread_b.start()

    # El primero en resolver es el ganador: su transacción sigue abierta (no hemos
    # comiteado todavía), así que si el otro hilo perdió la carrera del UPDATE, sigue
    # bloqueado dentro de PostgreSQL esperando exactamente ese commit.
    first_label, first_status, first_payload, first_jtis_or_exc, first_session = results.get(timeout=10)
    assert first_status == "success", "el primero en resolver debe ser el ganador de la rotación"

    # Suelta el lock: recién ahora el perdedor puede desbloquear su UPDATE.
    first_session.commit()

    second_label, second_status, second_payload, second_jtis_or_exc, second_session = results.get(timeout=10)

    thread_a.join(timeout=10)
    thread_b.join(timeout=10)
    assert not thread_a.is_alive(), "deadlock: el hilo A nunca terminó"
    assert not thread_b.is_alive(), "deadlock: el hilo B nunca terminó"

    assert {first_label, second_label} == {"a", "b"}
    assert second_status == "reuse", "el perdedor debe recibir RefreshReuseError (mismo trato que un reúso)"

    # Como en el router real (_blacklist_jtis_then_commit), el branch de reúso también
    # confirma: revoke_family(commit=False) ya quedó flusheado, esto lo persiste.
    second_session.commit()
    second_session.close()
    first_session.close()

    winner_response = first_payload

    with Session(pg_engine) as session:
        repo = RefreshTokenRepository(session)
        original = repo.get_by_hash(hash_token(ctx["raw_refresh"]))
        winner_row = repo.get_by_hash(hash_token(winner_response["refresh_token"]))

        family_members = list(session.exec(select(RefreshToken).where(RefreshToken.family_id == original.family_id)))
        assert len(family_members) == 2, "el canje concurrente no debe crear mas de un sucesor"

        # Estado final documentado: la detección de reúso revoca TODA la familia como
        # medida de seguridad existente (no introducida por este fix), incluso cuando la
        # "reutilización" fue en realidad una carrera legítima entre dos requests del
        # mismo cliente. El token recién emitido al ganador queda revocado también.
        assert original.status == "revoked"
        assert winner_row is not None
        assert winner_row.status == "revoked"
