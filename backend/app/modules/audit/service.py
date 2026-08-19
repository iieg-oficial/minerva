from sqlmodel import Session

from app.modules.audit.models import AuditLog
from app.modules.audit.repository import AuditRepository
from app.modules.audit.schemas import AuditLogRead


class AuditService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = AuditRepository(session)

    def log(
        self,
        action: str,
        actor_user_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        application_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        event_metadata: dict | None = None,
        commit: bool = True,
    ) -> AuditLog:
        log = AuditLog(
            action=action,
            actor_user_id=actor_user_id,
            target_type=target_type,
            target_id=target_id,
            application_id=application_id,
            ip_address=ip_address,
            user_agent=user_agent,
            event_metadata=event_metadata or {},
        )
        return self.repo.create(log, commit=commit)

    def list_logs(
        self,
        offset: int = 0,
        limit: int = 100,
        actor_user_id: str | None = None,
        action: str | None = None,
        target_type: str | None = None,
        application_id: str | None = None,
    ) -> tuple[list[AuditLogRead], int]:
        logs, total = self.repo.list_all(offset, limit, actor_user_id, action, target_type, application_id)
        return [AuditLogRead.model_validate(log) for log in logs], total
