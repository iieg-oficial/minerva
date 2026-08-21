from fastapi import APIRouter, Depends, Query, Request
from sqlmodel import Session

from app.core.dependencies.admin import require_minerva_admin
from app.core.dependencies.auth import get_current_panel_user
from app.core.dependencies.db import get_db
from app.modules.audit.service import AuditService
from app.modules.groups.schemas import GroupCreate, GroupRead, GroupUpdate
from app.modules.groups.service import GroupService
from app.shared.pagination import PaginatedResponse

router = APIRouter(prefix="/groups", tags=["Groups"], dependencies=[Depends(require_minerva_admin)])


def get_group_service(session: Session = Depends(get_db)) -> GroupService:
    return GroupService(session)


def get_audit_service(session: Session = Depends(get_db)) -> AuditService:
    return AuditService(session)


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
    audit: AuditService = Depends(get_audit_service),
    _current_user: dict = Depends(get_current_panel_user),
):
    result = service.create_group(data, commit=False)
    audit.log(
        "group_create",
        actor_user_id=_current_user["sub"],
        target_type="group",
        target_id=result.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        event_metadata={"result": "success"},
    )
    return result


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
    request: Request,
    service: GroupService = Depends(get_group_service),
    audit: AuditService = Depends(get_audit_service),
    _current_user: dict = Depends(get_current_panel_user),
):
    result = service.update_group(group_id, data, commit=False)
    audit.log(
        "group_update",
        actor_user_id=_current_user["sub"],
        target_type="group",
        target_id=group_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        event_metadata={"result": "success"},
    )
    return result


@router.post("/{group_id}/users/{user_id}", status_code=201)
def add_user_to_group(
    group_id: str,
    user_id: str,
    request: Request,
    service: GroupService = Depends(get_group_service),
    audit: AuditService = Depends(get_audit_service),
    _current_user: dict = Depends(get_current_panel_user),
):
    service.add_user_to_group(group_id, user_id, commit=False)
    audit.log(
        "group_user_add",
        actor_user_id=_current_user["sub"],
        target_type="group_user",
        target_id=f"{group_id}:{user_id}",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        event_metadata={"result": "success"},
    )
    return {"message": "Usuario agregado al grupo"}


@router.delete("/{group_id}/users/{user_id}", status_code=204)
def remove_user_from_group(
    group_id: str,
    user_id: str,
    request: Request,
    service: GroupService = Depends(get_group_service),
    audit: AuditService = Depends(get_audit_service),
    _current_user: dict = Depends(get_current_panel_user),
):
    service.remove_user_from_group(group_id, user_id, commit=False)
    audit.log(
        "group_user_remove",
        actor_user_id=_current_user["sub"],
        target_type="group_user",
        target_id=f"{group_id}:{user_id}",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        event_metadata={"result": "success"},
    )


@router.post("/{group_id}/roles/{role_id}", status_code=201)
def add_role_to_group(
    group_id: str,
    role_id: str,
    request: Request,
    service: GroupService = Depends(get_group_service),
    audit: AuditService = Depends(get_audit_service),
    _current_user: dict = Depends(get_current_panel_user),
):
    application_id = service.add_role_to_group(group_id, role_id, commit=False)
    audit.log(
        "group_role_add",
        actor_user_id=_current_user["sub"],
        target_type="group_role",
        target_id=f"{group_id}:{role_id}",
        application_id=application_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        event_metadata={"result": "success"},
    )
    return {"message": "Rol asignado al grupo"}


@router.delete("/{group_id}/roles/{role_id}", status_code=204)
def remove_role_from_group(
    group_id: str,
    role_id: str,
    request: Request,
    service: GroupService = Depends(get_group_service),
    audit: AuditService = Depends(get_audit_service),
    _current_user: dict = Depends(get_current_panel_user),
):
    application_id = service.remove_role_from_group(group_id, role_id, commit=False)
    audit.log(
        "group_role_remove",
        actor_user_id=_current_user["sub"],
        target_type="group_role",
        target_id=f"{group_id}:{role_id}",
        application_id=application_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        event_metadata={"result": "success"},
    )


@router.post("/users/{user_id}/roles/{role_id}", status_code=201)
def assign_role_to_user(
    user_id: str,
    role_id: str,
    request: Request,
    service: GroupService = Depends(get_group_service),
    audit: AuditService = Depends(get_audit_service),
    _current_user: dict = Depends(get_current_panel_user),
):
    application_id = service.assign_role_to_user(user_id, role_id, commit=False)
    audit.log(
        "user_role_add",
        actor_user_id=_current_user["sub"],
        target_type="user_role",
        target_id=f"{user_id}:{role_id}",
        application_id=application_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        event_metadata={"result": "success"},
    )
    return {"message": "Rol asignado al usuario"}


@router.delete("/users/{user_id}/roles/{role_id}", status_code=204)
def remove_role_from_user(
    user_id: str,
    role_id: str,
    request: Request,
    service: GroupService = Depends(get_group_service),
    audit: AuditService = Depends(get_audit_service),
    _current_user: dict = Depends(get_current_panel_user),
):
    application_id = service.remove_role_from_user(user_id, role_id, commit=False)
    audit.log(
        "user_role_remove",
        actor_user_id=_current_user["sub"],
        target_type="user_role",
        target_id=f"{user_id}:{role_id}",
        application_id=application_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        event_metadata={"result": "success"},
    )
