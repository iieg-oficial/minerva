from fastapi import APIRouter, Depends, Query, Request
from sqlmodel import Session

from app.core.dependencies.admin import require_minerva_admin
from app.core.dependencies.auth import get_current_panel_user
from app.core.dependencies.db import get_db
from app.modules.audit.service import AuditService
from app.modules.permissions.schemas import PermissionRead
from app.modules.permissions.service import PermissionService
from app.modules.roles.schemas import RoleCreate, RoleRead, RoleUpdate
from app.modules.roles.service import RoleService
from app.modules.users.schemas import UserRead
from app.shared.pagination import PaginatedResponse

router = APIRouter(prefix="/roles", tags=["Roles"], dependencies=[Depends(require_minerva_admin)])


def get_role_service(session: Session = Depends(get_db)) -> RoleService:
    return RoleService(session)


def get_permission_service(session: Session = Depends(get_db)) -> PermissionService:
    return PermissionService(session)


def get_audit_service(session: Session = Depends(get_db)) -> AuditService:
    return AuditService(session)


@router.get("", response_model=PaginatedResponse[RoleRead])
def list_roles(
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    application_id: str | None = Query(None),
    service: RoleService = Depends(get_role_service),
    _current_user: dict = Depends(get_current_panel_user),
):
    if application_id:
        roles = service.list_roles_by_application(application_id)
        return PaginatedResponse.create(roles, len(roles))
    roles, total = service.list_roles(offset, limit)
    return PaginatedResponse.create(roles, total)


@router.post("", response_model=RoleRead, status_code=201)
def create_role(
    data: RoleCreate,
    request: Request,
    application_id: str = Query(..., description="ID de la aplicación"),
    service: RoleService = Depends(get_role_service),
    audit: AuditService = Depends(get_audit_service),
    _current_user: dict = Depends(get_current_panel_user),
):
    result = service.create_role(application_id, data, commit=False)
    audit.log(
        "role_create",
        actor_user_id=_current_user["sub"],
        target_type="role",
        target_id=result.id,
        application_id=application_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        event_metadata={"result": "success"},
    )
    return result


@router.get("/{role_id}", response_model=RoleRead)
def get_role(
    role_id: str,
    service: RoleService = Depends(get_role_service),
    _current_user: dict = Depends(get_current_panel_user),
):
    return service.get_role(role_id)


@router.get("/{role_id}/permissions", response_model=list[PermissionRead])
def list_role_permissions(
    role_id: str,
    service: PermissionService = Depends(get_permission_service),
    _current_user: dict = Depends(get_current_panel_user),
):
    return service.list_permissions_by_role(role_id)


@router.get("/{role_id}/users", response_model=list[UserRead])
def list_role_users(
    role_id: str,
    service: RoleService = Depends(get_role_service),
    _current_user: dict = Depends(get_current_panel_user),
):
    return service.list_users_for_role(role_id)


@router.patch("/{role_id}", response_model=RoleRead)
def update_role(
    role_id: str,
    data: RoleUpdate,
    request: Request,
    service: RoleService = Depends(get_role_service),
    audit: AuditService = Depends(get_audit_service),
    _current_user: dict = Depends(get_current_panel_user),
):
    result = service.update_role(role_id, data, commit=False)
    audit.log(
        "role_update",
        actor_user_id=_current_user["sub"],
        target_type="role",
        target_id=role_id,
        application_id=result.application_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        event_metadata={"result": "success"},
    )
    return result


@router.delete("/{role_id}", status_code=204)
def delete_role(
    role_id: str,
    request: Request,
    service: RoleService = Depends(get_role_service),
    audit: AuditService = Depends(get_audit_service),
    _current_user: dict = Depends(get_current_panel_user),
):
    application_id = service.delete_role(role_id, commit=False)
    audit.log(
        "role_delete",
        actor_user_id=_current_user["sub"],
        target_type="role",
        target_id=role_id,
        application_id=application_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        event_metadata={"result": "success"},
    )


@router.post("/{role_id}/permissions/{permission_id}", status_code=201)
def add_permission_to_role(
    role_id: str,
    permission_id: str,
    request: Request,
    service: PermissionService = Depends(get_permission_service),
    audit: AuditService = Depends(get_audit_service),
    _current_user: dict = Depends(get_current_panel_user),
):
    application_id = service.add_permission_to_role(role_id, permission_id, commit=False)
    audit.log(
        "role_permission_add",
        actor_user_id=_current_user["sub"],
        target_type="role_permission",
        target_id=f"{role_id}:{permission_id}",
        application_id=application_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        event_metadata={"result": "success"},
    )
    return {"message": "Permiso asignado al rol"}


@router.delete("/{role_id}/permissions/{permission_id}", status_code=204)
def remove_permission_from_role(
    role_id: str,
    permission_id: str,
    request: Request,
    service: PermissionService = Depends(get_permission_service),
    audit: AuditService = Depends(get_audit_service),
    _current_user: dict = Depends(get_current_panel_user),
):
    application_id = service.remove_permission_from_role(role_id, permission_id, commit=False)
    audit.log(
        "role_permission_remove",
        actor_user_id=_current_user["sub"],
        target_type="role_permission",
        target_id=f"{role_id}:{permission_id}",
        application_id=application_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        event_metadata={"result": "success"},
    )
