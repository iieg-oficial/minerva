"""El invariante «una sola clave `active` y una sola `pending`» lo garantiza la BD.

Los índices únicos parciales de la migración 009 son PostgreSQL/SQLite-específicos y la
carrera solo es real con transacciones concurrentes de verdad, así que estas pruebas
corren contra el PostgreSQL de MINERVA_TEST_POSTGRES_URL o se saltan.
"""

import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlmodel import Session, select

from app.core.exceptions import ConflictError
from app.core.models import import_models
from app.modules.oidc.models import SigningKey
from app.modules.oidc.repository import SigningKeyRepository
from app.modules.oidc.service import OIDCService
from tests.conftest import require_test_database_url

PG_URL = os.environ.get("MINERVA_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(
    not PG_URL,
    reason="requiere MINERVA_TEST_POSTGRES_URL apuntando a un PostgreSQL real (indices unicos parciales)",
)

BACKEND_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture
def migrated_engine():
    require_test_database_url(PG_URL)
    reset_engine = create_engine(PG_URL, isolation_level="AUTOCOMMIT")
    with reset_engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    reset_engine.dispose()

    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        # Las dos: Alembic usa `effective_db_url` y MINERVA_DB_URL tiene prioridad.
        env={**os.environ, "DATABASE_URL": PG_URL, "MINERVA_DB_URL": PG_URL},
        check=True,
    )

    import_models()
    engine = create_engine(PG_URL, echo=False)
    yield engine
    engine.dispose()


def _count(engine, status: str) -> int:
    with Session(engine) as session:
        return len(session.exec(select(SigningKey).where(SigningKey.status == status)).all())


def test_dos_stage_key_concurrentes_dejan_una_sola_pendiente(migrated_engine):
    """Dos operadores publican una clave a la vez. Hilos de verdad con su propia Session:
    una barrera los suelta juntos para que ambos pasen la comprobación del service antes
    de que ninguno haya comiteado.

    Gane quien gane, el resultado debe ser el mismo: exactamente una pendiente y un
    `ConflictError` para el perdedor (lo atrape la comprobación previa o el índice único,
    que es el único que cierra la ventana cuando ambos ya comprobaron)."""
    with Session(migrated_engine) as session:
        OIDCService(session).ensure_active_signing_key()

    barrier = threading.Barrier(2)
    results: queue.Queue = queue.Queue()

    def _stage():
        with Session(migrated_engine) as session:
            service = OIDCService(session)
            service.repo.get_pending()  # la comprobación que ambos hacen antes de insertar
            barrier.wait(timeout=10)
            try:
                results.put(("ok", service.stage_key().kid))
            except ConflictError as exc:
                results.put(("conflict", str(exc)))

    threads = [threading.Thread(target=_stage) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
        assert not thread.is_alive(), "un stage_key se quedó bloqueado"

    outcomes = [results.get() for _ in range(2)]
    kinds = sorted(kind for kind, _ in outcomes)
    assert kinds == ["conflict", "ok"], f"esperaba un ganador y un conflicto, hubo {kinds}"

    assert _count(migrated_engine, "pending") == 1
    winner_kid = next(value for kind, value in outcomes if kind == "ok")
    with Session(migrated_engine) as session:
        assert OIDCService(session).repo.get_pending().kid == winner_kid


def test_dos_ensure_active_concurrentes_convergen_a_la_misma_clave(migrated_engine, monkeypatch):
    """Con varios workers, todos siembran a la vez sobre una tabla vacía al arrancar.
    Ninguno debe fallar: el perdedor del índice se queda con la clave del ganador, así
    que ambos terminan bien y con el mismo `kid`.

    La barrera se mete DENTRO de `ensure_active_signing_key`, justo después del
    `get_active()` con el que decide si hay que crear la clave: sincronizar antes de
    llamarlo no sirve, porque el ganador podría comitear antes de que el otro haga esa
    consulta y entonces se saldría por el camino fácil sin tocar el INSERT. Así el
    camino de `IntegrityError` se ejercita siempre, no cuando lo quiera el planificador.
    """
    barrier = threading.Barrier(2)
    results: queue.Queue = queue.Queue()
    local = threading.local()
    insert_attempts = queue.Queue()

    original_get_active = SigningKeyRepository.get_active
    original_generate = OIDCService.generate_signing_key

    def get_active_sincronizado(self):
        result = original_get_active(self)
        # Solo la PRIMERA consulta de cada hilo participante espera: la del camino de
        # recuperación tras el rollback no debe bloquearse, ni las del hilo principal.
        if getattr(local, "sync_pending", False):
            local.sync_pending = False
            barrier.wait(timeout=10)
        return result

    def generate_contado(self, status="active"):
        insert_attempts.put(status)
        return original_generate(self, status)

    monkeypatch.setattr(SigningKeyRepository, "get_active", get_active_sincronizado)
    monkeypatch.setattr(OIDCService, "generate_signing_key", generate_contado)

    def _ensure():
        with Session(migrated_engine) as session:
            service = OIDCService(session)
            local.sync_pending = True
            try:
                results.put(("ok", service.ensure_active_signing_key().kid))
            except Exception as exc:  # noqa: BLE001 - el test reporta el fallo
                results.put(("error", f"{type(exc).__name__}: {exc}"))

    threads = [threading.Thread(target=_ensure) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
        assert not thread.is_alive(), "un ensure_active_signing_key se quedó bloqueado"

    outcomes = [results.get() for _ in range(2)]
    errors = [value for kind, value in outcomes if kind == "error"]
    assert not errors, f"ningún caller debía fallar, pero: {errors}"

    # Ambos vieron la tabla vacía y ambos intentaron insertar: si solo hubiera un
    # intento, el perdedor se habría salido antes y el IntegrityError nunca se probaría.
    assert insert_attempts.qsize() == 2, "los dos hilos debían llegar al INSERT"

    kids = {value for _, value in outcomes}
    assert len(kids) == 1, f"ambos debían devolver el mismo kid, devolvieron {kids}"
    assert _count(migrated_engine, "active") == 1
    with Session(migrated_engine) as session:
        assert OIDCService(session).repo.get_active().kid == kids.pop()


def test_la_base_rechaza_una_segunda_pendiente(migrated_engine):
    """El índice, no el service: un INSERT directo con otra `pending` falla."""
    with Session(migrated_engine) as session:
        OIDCService(session).stage_key()

    with Session(migrated_engine) as session:
        session.add(SigningKey(kid="pendiente-intrusa", private_key_pem="x", public_key_pem="x", status="pending"))
        with pytest.raises(Exception, match="ux_signing_keys_single_pending"):
            session.commit()
        session.rollback()

    assert _count(migrated_engine, "pending") == 1


def test_la_base_rechaza_una_segunda_clave_activa(migrated_engine):
    """Ni siquiera saltándose el service: un INSERT directo con otra `active` falla."""
    with Session(migrated_engine) as session:
        OIDCService(session).ensure_active_signing_key()

    with Session(migrated_engine) as session:
        session.add(SigningKey(kid="kid-intruso", private_key_pem="x", public_key_pem="x", status="active"))
        with pytest.raises(Exception, match="ux_signing_keys_single_active"):
            session.commit()
        session.rollback()

    assert _count(migrated_engine, "active") == 1


def test_promover_no_viola_el_invariante(migrated_engine):
    """El camino feliz sigue funcionando con los índices puestos: retirar la activa y
    activar la pendiente ocurre en una transacción, sin pasar por dos activas."""
    with Session(migrated_engine) as session:
        service = OIDCService(session)
        original_kid = service.ensure_active_signing_key().kid
        service.stage_key()
        promoted_kid = service.promote_key(force=True).kid

    assert _count(migrated_engine, "active") == 1
    assert _count(migrated_engine, "pending") == 0
    with Session(migrated_engine) as session:
        repo = OIDCService(session).repo
        assert repo.get_active().kid == promoted_kid
        assert repo.get_by_kid(original_kid).status == "retired"


def test_varias_retiradas_siguen_permitidas(migrated_engine):
    """El invariante es solo sobre `active`/`pending`: la ventana de solapamiento exige
    poder tener varias retiradas publicadas a la vez."""
    with Session(migrated_engine) as session:
        service = OIDCService(session)
        service.ensure_active_signing_key()
        for _ in range(3):
            service.stage_key()
            service.promote_key(force=True)

    assert _count(migrated_engine, "retired") == 3
    assert _count(migrated_engine, "active") == 1
