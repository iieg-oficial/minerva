from datetime import datetime, timezone

from sqlmodel import Session, select

from app.modules.roles.models import Role


class RoleRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, role_id: str) -> Role | None:
        return self.session.get(Role, role_id)

    def get_by_slug(self, app_id: str, slug: str) -> Role | None:
        statement = select(Role).where(Role.application_id == app_id, Role.slug == slug)
        return self.session.exec(statement).first()

    def list_by_application(self, app_id: str) -> list[Role]:
        statement = select(Role).where(Role.application_id == app_id)
        return self.session.exec(statement).all()

    def list_all(self, offset: int = 0, limit: int = 100) -> tuple[list[Role], int]:
        statement = select(Role).offset(offset).limit(limit)
        items = self.session.exec(statement).all()
        total = self.session.exec(select(Role)).all()
        return items, len(total)

    def create(self, role: Role, commit: bool = True) -> Role:
        self.session.add(role)
        if commit:
            self.session.commit()
            self.session.refresh(role)
        else:
            self.session.flush()
        return role

    def update(self, role: Role, commit: bool = True) -> Role:
        role.updated_at = datetime.now(timezone.utc)
        self.session.add(role)
        if commit:
            self.session.commit()
            self.session.refresh(role)
        else:
            self.session.flush()
        return role

    def delete(self, role: Role, commit: bool = True) -> None:
        self.session.delete(role)
        self.session.commit() if commit else self.session.flush()
