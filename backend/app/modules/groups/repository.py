from datetime import datetime, timezone

from sqlmodel import Session, select

from app.modules.groups.models import Group, GroupRole, GroupUser, UserRole
from app.modules.roles.models import Role
from app.modules.users.models import User


class GroupRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, group_id: str) -> Group | None:
        return self.session.get(Group, group_id)

    def get_by_slug(self, slug: str) -> Group | None:
        statement = select(Group).where(Group.slug == slug)
        return self.session.exec(statement).first()

    def list_all(self, offset: int = 0, limit: int = 100) -> tuple[list[Group], int]:
        statement = select(Group).offset(offset).limit(limit)
        items = self.session.exec(statement).all()
        total = self.session.exec(select(Group)).all()
        return items, len(total)

    def create(self, group: Group, commit: bool = True) -> Group:
        self.session.add(group)
        if commit:
            self.session.commit()
            self.session.refresh(group)
        else:
            self.session.flush()
        return group

    def update(self, group: Group, commit: bool = True) -> Group:
        group.updated_at = datetime.now(timezone.utc)
        self.session.add(group)
        if commit:
            self.session.commit()
            self.session.refresh(group)
        else:
            self.session.flush()
        return group

    def delete(self, group: Group) -> None:
        self.session.delete(group)
        self.session.commit()


class GroupUserRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, gu: GroupUser, commit: bool = True) -> GroupUser:
        self.session.add(gu)
        self.session.commit() if commit else self.session.flush()
        return gu

    def remove(self, gu: GroupUser, commit: bool = True) -> None:
        self.session.delete(gu)
        self.session.commit() if commit else self.session.flush()

    def get(self, group_id: str, user_id: str) -> GroupUser | None:
        statement = select(GroupUser).where(GroupUser.group_id == group_id, GroupUser.user_id == user_id)
        return self.session.exec(statement).first()

    def list_users_in_group(self, group_id: str) -> list[str]:
        statement = select(GroupUser.user_id).where(GroupUser.group_id == group_id)
        return self.session.exec(statement).all()

    def list_groups_for_user(self, user_id: str) -> list[str]:
        statement = select(GroupUser.group_id).where(GroupUser.user_id == user_id)
        return self.session.exec(statement).all()


class GroupRoleRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, gr: GroupRole, commit: bool = True) -> GroupRole:
        self.session.add(gr)
        self.session.commit() if commit else self.session.flush()
        return gr

    def remove(self, gr: GroupRole, commit: bool = True) -> None:
        self.session.delete(gr)
        self.session.commit() if commit else self.session.flush()

    def get(self, group_id: str, role_id: str) -> GroupRole | None:
        statement = select(GroupRole).where(GroupRole.group_id == group_id, GroupRole.role_id == role_id)
        return self.session.exec(statement).first()

    def list_roles_for_group(self, group_id: str) -> list[Role]:
        statement = select(Role).join(GroupRole).where(GroupRole.group_id == group_id)
        return self.session.exec(statement).all()

    def remove_all_for_role(self, role_id: str, commit: bool = True) -> None:
        links = self.session.exec(select(GroupRole).where(GroupRole.role_id == role_id)).all()
        for link in links:
            self.session.delete(link)
        self.session.commit() if commit else self.session.flush()


class UserRoleRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, ur: UserRole, commit: bool = True) -> UserRole:
        self.session.add(ur)
        self.session.commit() if commit else self.session.flush()
        return ur

    def remove(self, ur: UserRole, commit: bool = True) -> None:
        self.session.delete(ur)
        self.session.commit() if commit else self.session.flush()

    def get(self, user_id: str, role_id: str) -> UserRole | None:
        statement = select(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role_id)
        return self.session.exec(statement).first()

    def list_roles_for_user(self, user_id: str) -> list[Role]:
        statement = select(Role).join(UserRole).where(UserRole.user_id == user_id)
        return self.session.exec(statement).all()

    def list_users_for_role(self, role_id: str) -> list[User]:
        statement = select(User).join(UserRole).where(UserRole.role_id == role_id)
        return self.session.exec(statement).all()

    def remove_all_for_role(self, role_id: str, commit: bool = True) -> None:
        links = self.session.exec(select(UserRole).where(UserRole.role_id == role_id)).all()
        for link in links:
            self.session.delete(link)
        self.session.commit() if commit else self.session.flush()
