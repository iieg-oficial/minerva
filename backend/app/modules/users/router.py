from fastapi import APIRouter, Depends, Query, Request
from redis.asyncio import Redis
from sqlmodel import Session

from app.core.config import settings
from app.core.dependencies.admin import require_minerva_admin
from app.core.dependencies.auth import get_current_panel_user
from app.core.dependencies.db import get_db
from app.core.redis import get_redis
from app.core.token_blacklist import invalidate_user_tokens, revoke_jti
from app.modules.users.schemas import UserCreate, UserRead, UserStatusUpdate, UserUpdate
from app.modules.users.service import UserService
from app.shared.pagination import PaginatedResponse

router = APIRouter(prefix="/users", tags=["Users"], dependencies=[Depends(require_minerva_admin)])


def get_user_service(session: Session = Depends(get_db)) -> UserService:
    return UserService(session)


async def _invalidate_user_sessions(redis: Redis, service: UserService, user_id: str) -> None:
    """Mata las sesiones/tokens vigentes del usuario tras cambiar sus credenciales o
    status: (1) revoca sus refresh tokens OIDC y blacklistea sus access_jti, y
    (2) marca el corte por `iat` para los bearer/sesión del panel que valida el backend."""
    jtis = service.revoke_refresh_tokens(user_id)
    access_ttl = settings.MINERVA_ACCESS_TOKEN_TTL_MINUTES * 60
    for jti in jtis:
        await revoke_jti(redis, jti, access_ttl)
    await invalidate_user_tokens(redis, user_id, settings.effective_token_expire_minutes * 60)


@router.get("", response_model=PaginatedResponse[UserRead])
def list_users(
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    service: UserService = Depends(get_user_service),
    _current_user: dict = Depends(get_current_panel_user),
):
    users, total = service.list_users(offset, limit)
    return PaginatedResponse.create(users, total)


@router.get("/{user_id}", response_model=UserRead)
def get_user(
    user_id: str,
    service: UserService = Depends(get_user_service),
    _current_user: dict = Depends(get_current_panel_user),
):
    return service.get_user(user_id)


@router.post("", response_model=UserRead, status_code=201)
def create_user(
    data: UserCreate,
    request: Request,
    service: UserService = Depends(get_user_service),
    _current_user: dict = Depends(get_current_panel_user),
):
    return service.create_user(data)


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: str,
    data: UserUpdate,
    service: UserService = Depends(get_user_service),
    redis: Redis = Depends(get_redis),
    _current_user: dict = Depends(get_current_panel_user),
):
    result = service.update_user(user_id, data)
    # Cambiar contraseña, correo o desactivar invalida las sesiones vigentes.
    if data.password is not None or data.email is not None or (data.status is not None and data.status != "active"):
        await _invalidate_user_sessions(redis, service, user_id)
    return result


@router.patch("/{user_id}/status", response_model=UserRead)
async def update_user_status(
    user_id: str,
    data: UserStatusUpdate,
    service: UserService = Depends(get_user_service),
    redis: Redis = Depends(get_redis),
    _current_user: dict = Depends(get_current_panel_user),
):
    result = service.update_status(user_id, data)
    if data.status != "active":
        await _invalidate_user_sessions(redis, service, user_id)
    return result
