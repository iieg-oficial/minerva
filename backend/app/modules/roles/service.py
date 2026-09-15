from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.core.constants import MINERVA_APP_SLUG, RESERVED_ROLE_PREFIX
from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.modules.applications.repository import ApplicationRepository
from app.modules.groups.repository import GroupRoleRepository, UserRoleRepository
from app.modules.permissions.repository import RolePermissionRepository
from app.modules.roles.models import Role
from app.modules.roles.repository import RoleRepository
from app.modules.roles.schemas import RoleCreate, RoleRead, RoleUpdate
from app.modules.users.schemas import UserRead


class RoleService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = RoleRepository(session)
        self.app_repo = ApplicationRepository(session)
        self.user_role_repo = UserRoleRepository(session)
        self.group_role_repo = GroupRoleRepository(session)
        self.role_perm_repo = RolePermissionRepository(session)

    def get_role(self, role_id: str) -> RoleRead:
        role = self.repo.get_by_id(role_id)
        if not role:
            raise NotFoundError(detail="Rol no encontrado")
        return RoleRead.model_validate(role)

    def list_roles_by_application(self, app_id: str) -> list[RoleRead]:
        roles = self.repo.list_by_application(app_id)
        return [RoleRead.model_validate(r) for r in roles]

    def list_roles(self, offset: int = 0, limit: int = 100) -> tuple[list[RoleRead], int]:
        roles, total = self.repo.list_all(offset, limit)
        return [RoleRead.model_validate(r) for r in roles], total

    def create_role(self, app_id: str, data: RoleCreate, commit: bool = True) -> RoleRead:
        if data.slug.startswith(RESERVED_ROLE_PREFIX) and not self._is_minerva_app(app_id):
            raise BadRequestError(detail="El prefijo 'minerva.' está reservado para los roles de la aplicación minerva")

        existing = self.repo.get_by_slug(app_id, data.slug)
        if existing:
            raise ConflictError(detail="Ya existe un rol con ese slug en esta aplicación")

        role = Role(application_id=app_id, name=data.name, slug=data.slug, description=data.description)
        try:
            role = self.repo.create(role, commit=commit)
        except IntegrityError:
            # La comprobación previa no cierra la carrera entre dos altas concurrentes;
            # el constraint de BD (issue #76) sí, y aquí se traduce a un 409 legible.
            self.session.rollback()
            raise ConflictError(detail="Ya existe un rol con ese slug en esta aplicación")
        return RoleRead.model_validate(role)

    def _is_minerva_app(self, app_id: str) -> bool:
        app = self.app_repo.get_by_id(app_id)
        return app is not None and app.slug == MINERVA_APP_SLUG

    def update_role(self, role_id: str, data: RoleUpdate, commit: bool = True) -> RoleRead:
        role = self.repo.get_by_id(role_id)
        if not role:
            raise NotFoundError(detail="Rol no encontrado")

        if data.name is not None:
            role.name = data.name
        if data.description is not None:
            role.description = data.description

        role = self.repo.update(role, commit=commit)
        return RoleRead.model_validate(role)

    def delete_role(self, role_id: str, commit: bool = True) -> str:
        role = self.repo.get_by_id(role_id)
        if not role:
            raise NotFoundError(detail="Rol no encontrado")
        # Elimina primero las relaciones para no violar llaves foráneas. Sin confirmar
        # (commit=False): si algo falla antes del borrado final, el rollback automático de
        # session.close() revierte todo el borrado en bloque (issue #75).
        self.role_perm_repo.remove_all_for_role(role_id, commit=False)
        self.user_role_repo.remove_all_for_role(role_id, commit=False)
        self.group_role_repo.remove_all_for_role(role_id, commit=False)
        self.repo.delete(role, commit=commit)
        return role.application_id

    def list_users_for_role(self, role_id: str) -> list[UserRead]:
        role = self.repo.get_by_id(role_id)
        if not role:
            raise NotFoundError(detail="Rol no encontrado")
        users = self.user_role_repo.list_users_for_role(role_id)
        return [UserRead.model_validate(u) for u in users]
