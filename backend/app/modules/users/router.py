from fastapi import APIRouter, Depends, Query, Request
from redis.asyncio import Redis
from sqlmodel import Session

from app.core.dependencies.admin import require_minerva_admin
from app.core.dependencies.auth import get_current_panel_user
from app.core.dependencies.db import get_db
from app.core.redis import get_redis
from app.modules.audit.service import AuditService
from app.modules.credentials.schemas import CredentialLink
from app.modules.credentials.service import CredentialService
from app.modules.users.invalidation import apply_with_invalidation
from app.modules.users.schemas import UserCreate, UserCreated, UserRead, UserStatusUpdate, UserUpdate
from app.modules.users.service import UserService
from app.shared.pagination import PaginatedResponse

router = APIRouter(prefix="/users", tags=["Users"], dependencies=[Depends(require_minerva_admin)])


def get_user_service(session: Session = Depends(get_db)) -> UserService:
    return UserService(session)


def get_audit_service(session: Session = Depends(get_db)) -> AuditService:
    return AuditService(session)


def get_credential_service(session: Session = Depends(get_db)) -> CredentialService:
    return CredentialService(session)


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


@router.post("", response_model=UserCreated, status_code=201)
def create_user(
    data: UserCreate,
    request: Request,
    service: UserService = Depends(get_user_service),
    credentials: CredentialService = Depends(get_credential_service),
    audit: AuditService = Depends(get_audit_service),
    _current_user: dict = Depends(get_current_panel_user),
):
    result = service.create_user(data, commit=False)
    # Sin contraseña: el usuario queda pendiente y el admin entrega el enlace de invitación.
    link = None if data.password else credentials.issue_link(result.id, created_by=_current_user["sub"], commit=False)
    audit.log(
        "user_create",
        actor_user_id=_current_user["sub"],
        target_type="user",
        target_id=result.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        event_metadata={"result": "success"},
        commit=link is None,
    )
    if link is not None:
        _audit_credential_link(audit, request, _current_user["sub"], result.id, link)
    return UserCreated(**result.model_dump(), credential_link=link)


def _audit_credential_link(
    audit: AuditService, request: Request, actor_id: str, user_id: str, link: CredentialLink
) -> None:
    audit.log(
        "credential_link_issue",
        actor_user_id=actor_id,
        target_type="user",
        target_id=user_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        event_metadata={"result": "success", "purpose": link.purpose},
    )


@router.post("/{user_id}/credential-link", response_model=CredentialLink, status_code=201)
def issue_credential_link(
    user_id: str,
    request: Request,
    credentials: CredentialService = Depends(get_credential_service),
    audit: AuditService = Depends(get_audit_service),
    _current_user: dict = Depends(get_current_panel_user),
):
    """Enlace de un solo uso para que la persona fije su contraseña: invitación si sigue
    pendiente, restablecimiento si ya estaba activa. Invalida los enlaces anteriores."""
    link = credentials.issue_link(user_id, created_by=_current_user["sub"], commit=False)
    _audit_credential_link(audit, request, _current_user["sub"], user_id, link)
    return link


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: str,
    data: UserUpdate,
    request: Request,
    service: UserService = Depends(get_user_service),
    audit: AuditService = Depends(get_audit_service),
    redis: Redis = Depends(get_redis),
    _current_user: dict = Depends(get_current_panel_user),
):
    # Cambiar contraseña, correo o desactivar invalida las sesiones vigentes.
    invalidating = (
        data.password is not None or data.email is not None or (data.status is not None and data.status != "active")
    )
    result = service.update_user(user_id, data, commit=False)
    audit.log(
        "user_update",
        actor_user_id=_current_user["sub"],
        target_type="user",
        target_id=user_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        event_metadata={"result": "success"},
        commit=not invalidating,
    )
    if invalidating:
        await apply_with_invalidation(service.session, redis, user_id)
    return result


@router.patch("/{user_id}/status", response_model=UserRead)
async def update_user_status(
    user_id: str,
    data: UserStatusUpdate,
    request: Request,
    service: UserService = Depends(get_user_service),
    audit: AuditService = Depends(get_audit_service),
    redis: Redis = Depends(get_redis),
    _current_user: dict = Depends(get_current_panel_user),
):
    invalidating = data.status != "active"
    result = service.update_status(user_id, data, commit=False)
    audit.log(
        "user_status_update",
        actor_user_id=_current_user["sub"],
        target_type="user",
        target_id=user_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        event_metadata={"result": "success"},
        commit=not invalidating,
    )
    if invalidating:
        await apply_with_invalidation(service.session, redis, user_id)
    return result
