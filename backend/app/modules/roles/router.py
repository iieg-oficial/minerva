from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.core.dependencies.auth import get_current_user
from app.core.dependencies.db import get_db
from app.modules.permissions.schemas import PermissionRead
from app.modules.permissions.service import PermissionService
from app.modules.roles.schemas import RoleCreate, RoleRead, RoleUpdate
from app.modules.roles.service import RoleService
from app.modules.users.schemas import UserRead
from app.shared.pagination import PaginatedResponse

router = APIRouter(prefix="/roles", tags=["Roles"])


def get_role_service(session: Session = Depends(get_db)) -> RoleService:
    return RoleService(session)


def get_permission_service(session: Session = Depends(get_db)) -> PermissionService:
    return PermissionService(session)


@router.get("", response_model=PaginatedResponse[RoleRead])
def list_roles(
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    application_id: str | None = Query(None),
    service: RoleService = Depends(get_role_service),
    _current_user: dict = Depends(get_current_user),
):
    if application_id:
        roles = service.list_roles_by_application(application_id)
        return PaginatedResponse.create(roles, len(roles))
    roles, total = service.list_roles(offset, limit)
    return PaginatedResponse.create(roles, total)


@router.post("", response_model=RoleRead, status_code=201)
def create_role(
    data: RoleCreate,
    application_id: str = Query(..., description="ID de la aplicación"),
    service: RoleService = Depends(get_role_service),
    _current_user: dict = Depends(get_current_user),
):
    return service.create_role(application_id, data)


@router.get("/{role_id}", response_model=RoleRead)
def get_role(
    role_id: str,
    service: RoleService = Depends(get_role_service),
    _current_user: dict = Depends(get_current_user),
):
    return service.get_role(role_id)


@router.get("/{role_id}/permissions", response_model=list[PermissionRead])
def list_role_permissions(
    role_id: str,
    service: PermissionService = Depends(get_permission_service),
    _current_user: dict = Depends(get_current_user),
):
    return service.list_permissions_by_role(role_id)


@router.get("/{role_id}/users", response_model=list[UserRead])
def list_role_users(
    role_id: str,
    service: RoleService = Depends(get_role_service),
    _current_user: dict = Depends(get_current_user),
):
    return service.list_users_for_role(role_id)


@router.patch("/{role_id}", response_model=RoleRead)
def update_role(
    role_id: str,
    data: RoleUpdate,
    service: RoleService = Depends(get_role_service),
    _current_user: dict = Depends(get_current_user),
):
    return service.update_role(role_id, data)


@router.delete("/{role_id}", status_code=204)
def delete_role(
    role_id: str,
    service: RoleService = Depends(get_role_service),
    _current_user: dict = Depends(get_current_user),
):
    service.delete_role(role_id)


@router.post("/{role_id}/permissions/{permission_id}", status_code=201)
def add_permission_to_role(
    role_id: str,
    permission_id: str,
    service: PermissionService = Depends(get_permission_service),
    _current_user: dict = Depends(get_current_user),
):
    service.add_permission_to_role(role_id, permission_id)
    return {"message": "Permiso asignado al rol"}


@router.delete("/{role_id}/permissions/{permission_id}", status_code=204)
def remove_permission_from_role(
    role_id: str,
    permission_id: str,
    service: PermissionService = Depends(get_permission_service),
    _current_user: dict = Depends(get_current_user),
):
    service.remove_permission_from_role(role_id, permission_id)
