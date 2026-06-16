from sqlmodel import Session, select

from app.modules.audit.models import AuditLog


class AuditRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, log: AuditLog) -> AuditLog:
        self.session.add(log)
        self.session.commit()
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
        statement = statement.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
        items = self.session.exec(statement).all()
        total = self.session.exec(select(AuditLog)).all()
        return items, len(total)
