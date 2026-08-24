from fastapi import APIRouter, Depends, Query, Request
from sqlmodel import Session

from app.core.dependencies.admin import require_minerva_admin
from app.core.dependencies.auth import get_current_panel_user
from app.core.dependencies.db import get_db
from app.modules.audit.service import AuditService
from app.modules.permissions.schemas import PermissionCreate, PermissionRead, PermissionUpdate
from app.modules.permissions.service import PermissionService
from app.shared.pagination import PaginatedResponse

router = APIRouter(prefix="/permissions", tags=["Permissions"], dependencies=[Depends(require_minerva_admin)])


def get_permission_service(session: Session = Depends(get_db)) -> PermissionService:
    return PermissionService(session)


def get_audit_service(session: Session = Depends(get_db)) -> AuditService:
    return AuditService(session)


@router.get("", response_model=PaginatedResponse[PermissionRead])
def list_permissions(
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    application_id: str | None = Query(None),
    service: PermissionService = Depends(get_permission_service),
    _current_user: dict = Depends(get_current_panel_user),
):
    if application_id:
        perms = service.list_permissions_by_application(application_id)
        return PaginatedResponse.create(perms, len(perms))
    perms, total = service.list_permissions(offset, limit)
    return PaginatedResponse.create(perms, total)


@router.post("", response_model=PermissionRead, status_code=201)
def create_permission(
    data: PermissionCreate,
    request: Request,
    application_id: str = Query(..., description="ID de la aplicación"),
    service: PermissionService = Depends(get_permission_service),
    audit: AuditService = Depends(get_audit_service),
    _current_user: dict = Depends(get_current_panel_user),
):
    result = service.create_permission(application_id, data, commit=False)
    audit.log(
        "permission_create",
        actor_user_id=_current_user["sub"],
        target_type="permission",
        target_id=result.id,
        application_id=application_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        event_metadata={"result": "success"},
    )
    return result


@router.get("/{permission_id}", response_model=PermissionRead)
def get_permission(
    permission_id: str,
    service: PermissionService = Depends(get_permission_service),
    _current_user: dict = Depends(get_current_panel_user),
):
    return service.get_permission(permission_id)


@router.patch("/{permission_id}", response_model=PermissionRead)
def update_permission(
    permission_id: str,
    data: PermissionUpdate,
    request: Request,
    service: PermissionService = Depends(get_permission_service),
    audit: AuditService = Depends(get_audit_service),
    _current_user: dict = Depends(get_current_panel_user),
):
    result = service.update_permission(permission_id, data, commit=False)
    audit.log(
        "permission_update",
        actor_user_id=_current_user["sub"],
        target_type="permission",
        target_id=permission_id,
        application_id=result.application_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        event_metadata={"result": "success"},
    )
    return result
