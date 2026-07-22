"""Rotación de claves de firma en dos fases: publish-before-use (issue #40).

Lo que se prueba es que rotar NO corta el servicio: la clave nueva se publica en el
JWKS antes de firmar con ella, un token emitido antes de la rotación sigue valiendo, y
un caché de JWKS viejo nunca produce un 401 espurio.
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session, select

from app.core.config import settings
from app.core.dependencies.auth import (
    JWKS_CACHE_KEY,
    _refresh_allowed,
    invalidate_jwks_cache,
)
from app.core.exceptions import ConflictError
from app.modules.oidc.models import SigningKey
from app.modules.oidc.service import OIDCService
from app.modules.users.models import User
from tests.conftest import test_engine


@pytest.fixture
def service():
    with Session(test_engine) as session:
        yield OIDCService(session)


def _active_kids() -> list[str]:
    with Session(test_engine) as session:
        return [k.kid for k in session.exec(select(SigningKey).where(SigningKey.status == "active")).all()]


# --- Fase 1: publicar sin firmar ------------------------------------------


def test_stage_publica_pending_sin_firmar_con_ella(service):
    original = service.ensure_active_signing_key()
    pending = service.stage_key()

    assert pending.status == "pending"
    # Ya está publicada: los verificadores pueden cachearla desde ahora.
    assert pending.kid in {entry["kid"] for entry in service.build_jwks()["keys"]}
    # Pero todavía NO firma nada: ese es el punto del publish-before-use.
    assert service.get_active_signing_key().kid == original.kid


def test_stage_rechaza_encadenar_dos_pendientes(service):
    service.ensure_active_signing_key()
    service.stage_key()

    with pytest.raises(ConflictError):
        service.stage_key()


# --- Fase 2: promover ------------------------------------------------------


def test_promote_antes_de_la_ventana_es_rechazado(service):
    service.ensure_active_signing_key()
    pending = service.stage_key()

    with pytest.raises(ConflictError, match="ventana de propagación"):
        service.promote_key()

    promoted = service.promote_key(force=True)
    assert promoted.kid == pending.kid
    assert service.get_active_signing_key().kid == pending.kid


def test_promote_pasada_la_ventana_no_necesita_force(service):
    service.ensure_active_signing_key()
    pending = service.stage_key()

    # Envejece la pendiente más allá de la ventana de propagación.
    stale_at = datetime.now(timezone.utc) - timedelta(minutes=settings.MINERVA_KEY_PROPAGATION_MINUTES + 1)
    pending.created_at = stale_at
    service.session.add(pending)
    service.session.commit()

    assert service.promote_key().kid == pending.kid


def test_promote_sin_pendiente_es_rechazado(service):
    service.ensure_active_signing_key()

    with pytest.raises(ConflictError, match="No hay ninguna clave pendiente"):
        service.promote_key()


def test_promociones_concurrentes_dejan_una_sola_activa(service):
    """Dos operaciones que promueven la misma pendiente: la segunda no debe dejar el
    sistema sin clave activa ni con dos. Patrón del issue #38: cada una con su Session,
    el UPDATE condicional decide el ganador."""
    original = service.ensure_active_signing_key()
    pending = service.stage_key()

    with Session(test_engine) as session_a, Session(test_engine) as session_b:
        repo_a, repo_b = OIDCService(session_a).repo, OIDCService(session_b).repo
        # Ambas leen la misma pendiente antes de que ninguna la reclame.
        claim_a, claim_b = repo_a.get_pending(), repo_b.get_pending()

        assert repo_a.promote(claim_a) is True
        assert repo_b.promote(claim_b) is False

    # La perdedora hizo rollback: no retiró la clave que la ganadora acababa de activar.
    assert _active_kids() == [pending.kid]
    with Session(test_engine) as session:
        assert OIDCService(session).repo.get_by_kid(original.kid).status == "retired"


# --- Ventana de retención de las claves retiradas --------------------------


def test_purga_respeta_la_vida_maxima_de_los_tokens_de_sesion(service):
    """Regresión: la purga usaba MINERVA_ACCESS_TOKEN_TTL_MINUTES (15 min) aunque los
    tokens `typ=session` viven 480 min. Una clave retirada hace 20 min todavía puede
    estar firmando sesiones de panel vigentes y NO debe borrarse."""
    assert settings.key_retirement_overlap_minutes > 20, "el default de sesión debería cubrir de sobra 20 min"

    retired = service.generate_signing_key()
    service.repo.mark_retired(retired)
    retired.rotated_at = datetime.now(timezone.utc) - timedelta(minutes=20)
    service.session.add(retired)
    service.session.commit()

    assert service.purge_expired_keys() == 0
    assert service.repo.get_by_kid(retired.kid) is not None
    assert retired.kid in {entry["kid"] for entry in service.build_jwks()["keys"]}


def test_purga_borra_las_retiradas_fuera_de_la_ventana(service):
    retired = service.generate_signing_key()
    service.repo.mark_retired(retired)
    retired.rotated_at = datetime.now(timezone.utc) - timedelta(minutes=settings.key_retirement_overlap_minutes + 1)
    service.session.add(retired)
    service.session.commit()

    assert service.purge_expired_keys() == 1
    assert service.repo.get_by_kid(retired.kid) is None


# --- Sin corte de servicio (HTTP, extremo a extremo) -----------------------


@pytest.fixture
def panel_user(client):
    """Usuario real con clave de firma activa: `/auth/me` resuelve el `sub` en BD."""
    with Session(test_engine) as session:
        user = User(email="rotacion@iieg.gob.mx", full_name="Usuario Rotacion", status="active")
        session.add(user)
        session.commit()
        session.refresh(user)
        return user.id


def _mint_session_token(user_id: str) -> str:
    with Session(test_engine) as session:
        return OIDCService(session).issue_session_token(user_id, "rotacion@iieg.gob.mx", "Usuario Rotacion")


def test_token_previo_sigue_validando_tras_promover(client, panel_user):
    """El caso que la rotación rompía: un token firmado con la clave vieja debe seguir
    valiendo después de rotar, porque la retirada sigue publicada en el JWKS."""
    token = _mint_session_token(panel_user)
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200

    with Session(test_engine) as session:
        service = OIDCService(session)
        service.stage_key()
        service.promote_key(force=True)

    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_token_nuevo_valida_aunque_el_cache_jwks_este_viejo(client, panel_user, fresh_redis):
    """Corazón del arreglo: si el caché de Redis quedó con el JWKS previo a la rotación
    (p. ej. el CLI no pudo limpiarlo), el backend NO debe rechazar un token que él mismo
    acaba de firmar — lo reconstruye al ver el `kid` desconocido."""
    old_token = _mint_session_token(panel_user)
    # Puebla el caché con el JWKS anterior a la rotación.
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {old_token}"}).status_code == 200
    cached_before = json.loads(asyncio.run(fresh_redis.get(JWKS_CACHE_KEY)))

    with Session(test_engine) as session:
        service = OIDCService(session)
        service.stage_key()
        new_key = service.promote_key(force=True)
    new_token = _mint_session_token(panel_user)

    # El caché sigue sin conocer la clave nueva: exactamente el escenario del bug.
    assert new_key.kid not in {entry["kid"] for entry in cached_before["keys"]}

    assert client.get("/auth/me", headers={"Authorization": f"Bearer {new_token}"}).status_code == 200
    # Y el token viejo tampoco se rompió por el refresco.
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {old_token}"}).status_code == 200


def test_kid_inexistente_sigue_siendo_rechazado(client):
    """El auto-sanado no puede convertirse en un pase libre: un `kid` que no existe en
    la BD debe terminar en 401 igual que antes."""
    from app.core.security import create_access_token_rs256
    from app.modules.oidc.service import _generate_rsa_keypair

    foreign_private, _ = _generate_rsa_keypair()
    token = create_access_token_rs256(
        user_id="x",
        email="x@iieg.gob.mx",
        name="X",
        kid="kid-que-no-existe",
        private_key_pem=foreign_private,
        typ="session",
    )

    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


# --- Caché de JWKS: invalidación y cooldown --------------------------------


def test_invalidate_jwks_cache_borra_la_clave(client, panel_user, fresh_redis):
    token = _mint_session_token(panel_user)
    client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert asyncio.run(fresh_redis.get(JWKS_CACHE_KEY)) is not None

    asyncio.run(invalidate_jwks_cache(fresh_redis))

    assert asyncio.run(fresh_redis.get(JWKS_CACHE_KEY)) is None


def test_cooldown_deja_pasar_un_solo_refresco_por_ventana(fresh_redis):
    """Sin cooldown, tokens con `kid` inventado reconstruirían el JWKS desde BD en cada
    request contra un endpoint público sin autenticar."""
    assert asyncio.run(_refresh_allowed(fresh_redis)) is True
    assert asyncio.run(_refresh_allowed(fresh_redis)) is False
