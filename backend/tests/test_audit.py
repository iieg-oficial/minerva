from sqlmodel import Session, select

from app.modules.applications.models import Application
from app.modules.audit.models import AuditLog
from app.modules.audit.repository import AuditRepository
from app.modules.audit.service import AuditService
from tests.conftest import test_engine


def test_list_all_counts_the_same_combined_filters_as_items():
    with Session(test_engine) as session:
        app = Application(name="Audit app", slug="audit-app")
        other_app = Application(name="Other app", slug="other-app")
        session.add_all([app, other_app])
        session.commit()

        repo = AuditRepository(session)
        matching = [
            AuditLog(actor_user_id="actor", action="read", target_type="user", application_id=app.id),
            AuditLog(actor_user_id="actor", action="read", target_type="user", application_id=app.id),
        ]
        for log in [
            *matching,
            AuditLog(actor_user_id="other", action="read", target_type="user", application_id=app.id),
            AuditLog(actor_user_id="actor", action="write", target_type="user", application_id=app.id),
            AuditLog(actor_user_id="actor", action="read", target_type="role", application_id=app.id),
            AuditLog(actor_user_id="actor", action="read", target_type="user", application_id=other_app.id),
        ]:
            repo.create(log)

        items, total = repo.list_all(
            limit=1,
            actor_user_id="actor",
            action="read",
            target_type="user",
            application_id=app.id,
        )

        assert len(items) == 1
        assert total == len(matching)


def test_log_without_commit_rolls_back_with_the_business_change():
    with Session(test_engine) as session:
        app = Application(name="Pending app", slug="pending-app")
        session.add(app)
        AuditService(session).log("application_created", application_id=app.id, commit=False)
        session.rollback()

    with Session(test_engine) as session:
        assert session.get(Application, app.id) is None
        assert session.exec(select(AuditLog).where(AuditLog.action == "application_created")).first() is None
