"""Invalidación de las sesiones de un usuario tras cambiar sus credenciales o su status.

La usan la administración de usuarios, el canje de enlaces de credencial y el cambio de
contraseña propio: un solo lugar para el orden fail-closed Redis → PostgreSQL."""

from redis.asyncio import Redis
from sqlmodel import Session

from app.core.config import settings
from app.core.token_blacklist import invalidate_user_tokens, revoke_jti
from app.modules.users.service import UserService


async def _invalidate_user_sessions(redis: Redis, session: Session, user_id: str) -> None:
    """Mata las sesiones/tokens vigentes del usuario: (1) revoca sus refresh tokens OIDC
    (pendiente en PG) y blacklistea sus access_jti, y (2) marca el corte por `iat` para los
    bearer/sesión del panel.

    Deja la revocación de PG pendiente (commit=False): se confirma DESPUÉS de que estas
    escrituras en Redis tengan éxito. Si Redis falla, la excepción sale antes del commit y
    se hace rollback → el cambio de credenciales no queda durable sin su invalidación
    (fail-closed)."""
    jtis = UserService(session).revoke_refresh_tokens(user_id, commit=False)
    access_ttl = settings.MINERVA_ACCESS_TOKEN_TTL_MINUTES * 60
    for jti in jtis:
        await revoke_jti(redis, jti, access_ttl)
    await invalidate_user_tokens(redis, user_id, settings.effective_token_expire_minutes * 60)


async def apply_with_invalidation(session: Session, redis: Redis, user_id: str) -> None:
    """Confirma un cambio que invalida sesiones en el orden fail-closed: las invalidaciones
    van a Redis primero y solo entonces se confirma PostgreSQL. Si Redis falla, rollback
    (PG intacto); si PG falla después, queda una invalidación de más (fallo seguro)."""
    try:
        await _invalidate_user_sessions(redis, session, user_id)
    except Exception:
        session.rollback()
        raise
    session.commit()
