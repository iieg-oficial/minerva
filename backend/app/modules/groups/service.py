from sqlmodel import Session

from app.core.constants import MINERVA_APP_SLUG
from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.modules.applications.repository import ApplicationRepository
from app.modules.groups.models import Group, GroupRole, GroupUser, UserRole
from app.modules.groups.repository import GroupRepository, GroupRoleRepository, GroupUserRepository, UserRoleRepository
from app.modules.groups.schemas import GroupCreate, GroupRead, GroupUpdate
from app.modules.roles.repository import RoleRepository
from app.modules.users.models import USER_KIND_SERVICE
from app.modules.users.repository import UserRepository


class GroupService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = GroupRepository(session)
        self.user_repo = UserRepository(session)
        self.role_repo = RoleRepository(session)
        self.group_user_repo = GroupUserRepository(session)
        self.group_role_repo = GroupRoleRepository(session)
        self.user_role_repo = UserRoleRepository(session)
        self.app_repo = ApplicationRepository(session)

    def get_group(self, group_id: str) -> GroupRead:
        group = self.repo.get_by_id(group_id)
        if not group:
            raise NotFoundError(detail="Grupo no encontrado")
        return GroupRead.model_validate(group)

    def list_groups(self, offset: int = 0, limit: int = 100) -> tuple[list[GroupRead], int]:
        groups, total = self.repo.list_all(offset, limit)
        return [GroupRead.model_validate(g) for g in groups], total

    def create_group(self, data: GroupCreate, commit: bool = True) -> GroupRead:
        existing = self.repo.get_by_slug(data.slug)
        if existing:
            raise ConflictError(detail="Ya existe un grupo con ese slug")

        group = Group(
            name=data.name,
            slug=data.slug,
            description=data.description,
            source=data.source,
            external_group_id=data.external_group_id,
        )
        group = self.repo.create(group, commit=commit)
        return GroupRead.model_validate(group)

    def update_group(self, group_id: str, data: GroupUpdate, commit: bool = True) -> GroupRead:
        group = self.repo.get_by_id(group_id)
        if not group:
            raise NotFoundError(detail="Grupo no encontrado")

        if data.name is not None:
            group.name = data.name
        if data.description is not None:
            group.description = data.description

        group = self.repo.update(group, commit=commit)
        return GroupRead.model_validate(group)

    def add_user_to_group(self, group_id: str, user_id: str, commit: bool = True) -> None:
        group = self.repo.get_by_id(group_id)
        if not group:
            raise NotFoundError(detail="Grupo no encontrado")
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError(detail="Usuario no encontrado")
        if user.kind == USER_KIND_SERVICE:
            # Los roles de una cuenta de servicio se asignan directo y a la vista: un grupo
            # le heredaría en silencio los roles que alguien agregue después.
            raise BadRequestError(detail="Una cuenta de servicio no puede pertenecer a grupos")
        existing = self.group_user_repo.get(group_id, user_id)
        if existing:
            raise ConflictError(detail="El usuario ya pertenece al grupo")
        self.group_user_repo.add(GroupUser(group_id=group_id, user_id=user_id), commit=commit)

    def remove_user_from_group(self, group_id: str, user_id: str, commit: bool = True) -> None:
        gu = self.group_user_repo.get(group_id, user_id)
        if not gu:
            raise NotFoundError(detail="El usuario no pertenece al grupo")
        self.group_user_repo.remove(gu, commit=commit)

    def add_role_to_group(self, group_id: str, role_id: str, commit: bool = True) -> str:
        if not self.repo.get_by_id(group_id):
            raise NotFoundError(detail="Grupo no encontrado")
        role = self.role_repo.get_by_id(role_id)
        if not role:
            raise NotFoundError(detail="Rol no encontrado")
        existing = self.group_role_repo.get(group_id, role_id)
        if existing:
            raise ConflictError(detail="El rol ya está asignado al grupo")
        self.group_role_repo.add(GroupRole(group_id=group_id, role_id=role_id), commit=commit)
        return role.application_id

    def remove_role_from_group(self, group_id: str, role_id: str, commit: bool = True) -> str:
        gr = self.group_role_repo.get(group_id, role_id)
        if not gr:
            raise NotFoundError(detail="El rol no está asignado al grupo")
        role = self.role_repo.get_by_id(role_id)
        if not role:
            raise NotFoundError(detail="Rol no encontrado")
        self.group_role_repo.remove(gr, commit=commit)
        return role.application_id

    def assign_role_to_user(self, user_id: str, role_id: str, commit: bool = True) -> str:
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError(detail="Usuario no encontrado")
        role = self.role_repo.get_by_id(role_id)
        if not role:
            raise NotFoundError(detail="Rol no encontrado")
        if user.kind == USER_KIND_SERVICE and self._is_minerva_role(role.application_id):
            raise BadRequestError(detail="Una cuenta de servicio no puede recibir roles de Minerva")
        existing = self.user_role_repo.get(user_id, role_id)
        if existing:
            raise ConflictError(detail="El rol ya está asignado al usuario")
        self.user_role_repo.add(UserRole(user_id=user_id, role_id=role_id), commit=commit)
        return role.application_id

    def remove_role_from_user(self, user_id: str, role_id: str, commit: bool = True) -> str:
        ur = self.user_role_repo.get(user_id, role_id)
        if not ur:
            raise NotFoundError(detail="El rol no está asignado al usuario")
        role = self.role_repo.get_by_id(role_id)
        if not role:
            raise NotFoundError(detail="Rol no encontrado")
        self.user_role_repo.remove(ur, commit=commit)
        return role.application_id

    def _is_minerva_role(self, application_id: str) -> bool:
        app = self.app_repo.get_by_id(application_id)
        return app is not None and app.slug == MINERVA_APP_SLUG
