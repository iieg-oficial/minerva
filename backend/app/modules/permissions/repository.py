from datetime import datetime, timezone

from sqlmodel import Session, select

from app.modules.permissions.models import Permission, RolePermission


class PermissionRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, perm_id: str) -> Permission | None:
        return self.session.get(Permission, perm_id)

    def get_by_slug(self, app_id: str, slug: str) -> Permission | None:
        statement = select(Permission).where(Permission.application_id == app_id, Permission.slug == slug)
        return self.session.exec(statement).first()

    def list_by_application(self, app_id: str) -> list[Permission]:
        statement = select(Permission).where(Permission.application_id == app_id)
        return self.session.exec(statement).all()

    def list_all(self, offset: int = 0, limit: int = 100) -> tuple[list[Permission], int]:
        statement = select(Permission).offset(offset).limit(limit)
        items = self.session.exec(statement).all()
        total = self.session.exec(select(Permission)).all()
        return items, len(total)

    def create(self, perm: Permission, commit: bool = True) -> Permission:
        self.session.add(perm)
        if commit:
            self.session.commit()
            self.session.refresh(perm)
        else:
            self.session.flush()
        return perm

    def update(self, perm: Permission, commit: bool = True) -> Permission:
        perm.updated_at = datetime.now(timezone.utc)
        self.session.add(perm)
        if commit:
            self.session.commit()
            self.session.refresh(perm)
        else:
            self.session.flush()
        return perm


class RolePermissionRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, role_perm: RolePermission, commit: bool = True) -> RolePermission:
        self.session.add(role_perm)
        self.session.commit() if commit else self.session.flush()
        return role_perm

    def remove(self, role_perm: RolePermission, commit: bool = True) -> None:
        self.session.delete(role_perm)
        self.session.commit() if commit else self.session.flush()

    def get(self, role_id: str, perm_id: str) -> RolePermission | None:
        statement = select(RolePermission).where(
            RolePermission.role_id == role_id,
            RolePermission.permission_id == perm_id,
        )
        return self.session.exec(statement).first()

    def list_permissions_by_role(self, role_id: str) -> list[Permission]:
        statement = (
            select(Permission)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role_id)
        )
        return self.session.exec(statement).all()

    def list_roles_by_permission(self, perm_id: str) -> list[RolePermission]:
        statement = select(RolePermission).where(RolePermission.permission_id == perm_id)
        return self.session.exec(statement).all()

    def remove_all_for_role(self, role_id: str, commit: bool = True) -> None:
        links = self.session.exec(select(RolePermission).where(RolePermission.role_id == role_id)).all()
        for link in links:
            self.session.delete(link)
        self.session.commit() if commit else self.session.flush()
