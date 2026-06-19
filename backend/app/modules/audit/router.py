from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.core.dependencies.admin import require_minerva_admin
from app.core.dependencies.auth import get_current_user
from app.core.dependencies.db import get_db
from app.modules.audit.schemas import AuditLogRead
from app.modules.audit.service import AuditService
from app.shared.pagination import PaginatedResponse

router = APIRouter(prefix="/audit", tags=["Audit"], dependencies=[Depends(require_minerva_admin)])


def get_audit_service(session: Session = Depends(get_db)) -> AuditService:
    return AuditService(session)


@router.get("", response_model=PaginatedResponse[AuditLogRead])
def list_audit_logs(
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    actor_user_id: str | None = Query(None),
    action: str | None = Query(None),
    target_type: str | None = Query(None),
    application_id: str | None = Query(None),
    service: AuditService = Depends(get_audit_service),
    _current_user: dict = Depends(get_current_user),
):
    logs, total = service.list_logs(offset, limit, actor_user_id, action, target_type, application_id)
    return PaginatedResponse.create(logs, total)
