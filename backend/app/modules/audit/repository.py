from sqlalchemy import func
from sqlmodel import Session, select

from app.modules.audit.models import AuditLog


class AuditRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, log: AuditLog, commit: bool = True) -> AuditLog:
        self.session.add(log)
        if commit:
            self.session.commit()
        else:
            self.session.flush()
        return log

    def list_all(
        self,
        offset: int = 0,
        limit: int = 100,
        actor_user_id: str | None = None,
        action: str | None = None,
        target_type: str | None = None,
        application_id: str | None = None,
    ) -> tuple[list[AuditLog], int]:
        statement = select(AuditLog)
        if actor_user_id:
            statement = statement.where(AuditLog.actor_user_id == actor_user_id)
        if action:
            statement = statement.where(AuditLog.action == action)
        if target_type:
            statement = statement.where(AuditLog.target_type == target_type)
        if application_id:
            statement = statement.where(AuditLog.application_id == application_id)
        total = self.session.exec(select(func.count()).select_from(statement.subquery())).one()
        statement = statement.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
        items = self.session.exec(statement).all()
        return items, total
