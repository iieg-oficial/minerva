from fastapi import APIRouter, Depends, Query, Request
from sqlmodel import Session

from app.core.dependencies.admin import require_minerva_admin
from app.core.dependencies.auth import get_current_panel_user
from app.core.dependencies.db import get_db
from app.modules.groups.schemas import GroupCreate, GroupRead, GroupUpdate
from app.modules.groups.service import GroupService
from app.shared.pagination import PaginatedResponse

router = APIRouter(prefix="/groups", tags=["Groups"], dependencies=[Depends(require_minerva_admin)])


def get_group_service(session: Session = Depends(get_db)) -> GroupService:
    return GroupService(session)


@router.get("", response_model=PaginatedResponse[GroupRead])
def list_groups(
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    service: GroupService = Depends(get_group_service),
    _current_user: dict = Depends(get_current_panel_user),
):
    groups, total = service.list_groups(offset, limit)
    return PaginatedResponse.create(groups, total)


@router.post("", response_model=GroupRead, status_code=201)
def create_group(
    data: GroupCreate,
    request: Request,
    service: GroupService = Depends(get_group_service),
    _current_user: dict = Depends(get_current_panel_user),
):
    return service.create_group(data)


@router.get("/{group_id}", response_model=GroupRead)
def get_group(
    group_id: str,
    service: GroupService = Depends(get_group_service),
    _current_user: dict = Depends(get_current_panel_user),
):
    return service.get_group(group_id)


@router.patch("/{group_id}", response_model=GroupRead)
def update_group(
    group_id: str,
    data: GroupUpdate,
    service: GroupService = Depends(get_group_service),
    _current_user: dict = Depends(get_current_panel_user),
):
    return service.update_group(group_id, data)


@router.post("/{group_id}/users/{user_id}", status_code=201)
def add_user_to_group(
    group_id: str,
    user_id: str,
    service: GroupService = Depends(get_group_service),
    _current_user: dict = Depends(get_current_panel_user),
):
    service.add_user_to_group(group_id, user_id)
    return {"message": "Usuario agregado al grupo"}


@router.delete("/{group_id}/users/{user_id}", status_code=204)
def remove_user_from_group(
    group_id: str,
    user_id: str,
    service: GroupService = Depends(get_group_service),
    _current_user: dict = Depends(get_current_panel_user),
):
    service.remove_user_from_group(group_id, user_id)


@router.post("/{group_id}/roles/{role_id}", status_code=201)
def add_role_to_group(
    group_id: str,
    role_id: str,
    service: GroupService = Depends(get_group_service),
    _current_user: dict = Depends(get_current_panel_user),
):
    service.add_role_to_group(group_id, role_id)
    return {"message": "Rol asignado al grupo"}


@router.delete("/{group_id}/roles/{role_id}", status_code=204)
def remove_role_from_group(
    group_id: str,
    role_id: str,
    service: GroupService = Depends(get_group_service),
    _current_user: dict = Depends(get_current_panel_user),
):
    service.remove_role_from_group(group_id, role_id)


@router.post("/users/{user_id}/roles/{role_id}", status_code=201)
def assign_role_to_user(
    user_id: str,
    role_id: str,
    service: GroupService = Depends(get_group_service),
    _current_user: dict = Depends(get_current_panel_user),
):
    service.assign_role_to_user(user_id, role_id)
    return {"message": "Rol asignado al usuario"}


@router.delete("/users/{user_id}/roles/{role_id}", status_code=204)
def remove_role_from_user(
    user_id: str,
    role_id: str,
    service: GroupService = Depends(get_group_service),
    _current_user: dict = Depends(get_current_panel_user),
):
    service.remove_role_from_user(user_id, role_id)
