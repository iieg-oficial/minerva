from fastapi import APIRouter, Depends, Query, Request
from sqlmodel import Session

from app.core.dependencies.db import get_db
from app.core.dependencies.delegated import DelegatedContext, require_app_delegate
from app.modules.audit.service import AuditService
from app.modules.credentials.schemas import CredentialLink
from app.modules.delegated.schemas import (
    DelegatedRoleRead,
    DelegatedRolesUpdate,
    DelegatedUserCreate,
    DelegatedUserCreated,
    DelegatedUserRead,
)
from app.modules.delegated.service import DelegatedService

router = APIRouter(prefix="/delegated", tags=["Delegated"])


def get_delegated_service(
    ctx: DelegatedContext = Depends(require_app_delegate),
    session: Session = Depends(get_db),
) -> DelegatedService:
    return DelegatedService(session, ctx.application)


def get_audit_service(session: Session = Depends(get_db)) -> AuditService:
    return AuditService(session)


def _audit(
    audit: AuditService,
    request: Request,
    ctx: DelegatedContext,
    action: str,
    target_type: str,
    target_id: str,
    extra: dict | None = None,
) -> None:
    """El actor es la persona; `via` y `client_id` distinguen la delegación del panel."""
    audit.log(
        action,
        actor_user_id=ctx.actor_id,
        target_type=target_type,
        target_id=target_id,
        application_id=ctx.application.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        event_metadata={
            "result": "success",
            "via": "delegated",
            "client_id": ctx.application.client_id,
            **(extra or {}),
        },
    )


@router.get("/roles", response_model=list[DelegatedRoleRead])
def list_roles(service: DelegatedService = Depends(get_delegated_service)):
    return service.list_roles()


@router.get("/users", response_model=list[DelegatedUserRead])
def list_users(
    email: str | None = Query(default=None, max_length=255),
    service: DelegatedService = Depends(get_delegated_service),
):
    return service.list_users(email)


@router.post("/users", response_model=DelegatedUserCreated, status_code=201)
def create_user(
    data: DelegatedUserCreate,
    request: Request,
    ctx: DelegatedContext = Depends(require_app_delegate),
    service: DelegatedService = Depends(get_delegated_service),
    audit: AuditService = Depends(get_audit_service),
):
    result = service.create_user(ctx.actor_id, data)
    if result.created:
        _audit(audit, request, ctx, "user_create", "user", result.id, {"role_ids": data.role_ids})
    return result


@router.put("/users/{user_id}/roles", response_model=DelegatedUserRead)
def set_roles(
    user_id: str,
    data: DelegatedRolesUpdate,
    request: Request,
    ctx: DelegatedContext = Depends(require_app_delegate),
    service: DelegatedService = Depends(get_delegated_service),
    audit: AuditService = Depends(get_audit_service),
):
    result, changes = service.set_roles(ctx.actor_id, user_id, data.role_ids)
    _audit(audit, request, ctx, "user_roles_set", "user", user_id, changes)
    return result


@router.post("/users/{user_id}/credential-link", response_model=CredentialLink, status_code=201)
def issue_credential_link(
    user_id: str,
    request: Request,
    ctx: DelegatedContext = Depends(require_app_delegate),
    service: DelegatedService = Depends(get_delegated_service),
    audit: AuditService = Depends(get_audit_service),
):
    link = service.issue_link(ctx.actor_id, user_id)
    _audit(audit, request, ctx, "credential_link_issue", "user", user_id, {"purpose": link.purpose})
    return link
