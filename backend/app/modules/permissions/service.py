from sqlmodel import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.modules.permissions.models import Permission, RolePermission
from app.modules.permissions.repository import PermissionRepository, RolePermissionRepository
from app.modules.permissions.schemas import PermissionCreate, PermissionRead, PermissionUpdate
from app.modules.roles.repository import RoleRepository


class PermissionService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = PermissionRepository(session)
        self.role_repo = RoleRepository(session)
        self.role_perm_repo = RolePermissionRepository(session)

    def get_permission(self, perm_id: str) -> PermissionRead:
        perm = self.repo.get_by_id(perm_id)
        if not perm:
            raise NotFoundError(detail="Permiso no encontrado")
        return PermissionRead.model_validate(perm)

    def list_permissions_by_application(self, app_id: str) -> list[PermissionRead]:
        perms = self.repo.list_by_application(app_id)
        return [PermissionRead.model_validate(p) for p in perms]

    def list_permissions(self, offset: int = 0, limit: int = 100) -> tuple[list[PermissionRead], int]:
        perms, total = self.repo.list_all(offset, limit)
        return [PermissionRead.model_validate(p) for p in perms], total

    def create_permission(self, app_id: str, data: PermissionCreate) -> PermissionRead:
        existing = self.repo.get_by_slug(app_id, data.slug)
        if existing:
            raise ConflictError(detail="Ya existe un permiso con ese slug en esta aplicación")

        perm = Permission(application_id=app_id, name=data.name, slug=data.slug, description=data.description)
        perm = self.repo.create(perm)
        return PermissionRead.model_validate(perm)

    def update_permission(self, perm_id: str, data: PermissionUpdate) -> PermissionRead:
        perm = self.repo.get_by_id(perm_id)
        if not perm:
            raise NotFoundError(detail="Permiso no encontrado")

        if data.name is not None:
            perm.name = data.name
        if data.description is not None:
            perm.description = data.description

        perm = self.repo.update(perm)
        return PermissionRead.model_validate(perm)

    def add_permission_to_role(self, role_id: str, perm_id: str) -> None:
        role = self.role_repo.get_by_id(role_id)
        if not role:
            raise NotFoundError(detail="Rol no encontrado")

        perm = self.repo.get_by_id(perm_id)
        if not perm:
            raise NotFoundError(detail="Permiso no encontrado")

        existing = self.role_perm_repo.get(role_id, perm_id)
        if existing:
            raise ConflictError(detail="El permiso ya está asignado a este rol")

        self.role_perm_repo.add(RolePermission(role_id=role_id, permission_id=perm_id))

    def remove_permission_from_role(self, role_id: str, perm_id: str) -> None:
        rp = self.role_perm_repo.get(role_id, perm_id)
        if not rp:
            raise NotFoundError(detail="El permiso no está asignado a este rol")
        self.role_perm_repo.remove(rp)

    def list_permissions_by_role(self, role_id: str) -> list[PermissionRead]:
        perms = self.role_perm_repo.list_permissions_by_role(role_id)
        return [PermissionRead.model_validate(p) for p in perms]
