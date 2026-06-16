from fastapi import APIRouter, Depends, Query, Request
from sqlmodel import Session

from app.core.dependencies.auth import get_current_user
from app.core.dependencies.db import get_db
from app.modules.audit.service import AuditService
from app.modules.authorization.schemas import PermissionCheckRequest, PermissionCheckResponse
from app.modules.authorization.service import AuthorizationService

router = APIRouter(prefix="/authorization", tags=["Authorization"])


def get_authorization_service(session: Session = Depends(get_db)) -> AuthorizationService:
    return AuthorizationService(session)


def get_audit_service(session: Session = Depends(get_db)) -> AuditService:
    return AuditService(session)


@router.post("/check", response_model=PermissionCheckResponse)
def check_permission(
    data: PermissionCheckRequest,
    request: Request,
    service: AuthorizationService = Depends(get_authorization_service),
    audit: AuditService = Depends(get_audit_service),
    _current_user: dict = Depends(get_current_user),
):
    result = service.check_permission(data.user_id, data.application_slug, data.permission)
    audit.log(
        "permission_check_allowed" if result["allowed"] else "permission_check_denied",
        actor_user_id=data.user_id,
        application_id=data.application_slug,
        ip_address=request.client.host,
        user_agent=request.headers.get("user-agent"),
        event_metadata={"permission": data.permission},
    )
    return result


@router.get("/me/permissions")
def get_my_permissions(
    application_slug: str = Query(...),
    service: AuthorizationService = Depends(get_authorization_service),
    current_user: dict = Depends(get_current_user),
):
    return service.get_me_permissions(current_user["sub"], application_slug)
