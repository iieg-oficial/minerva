from sqlmodel import Session

from app.core.exceptions import NotFoundError
from app.modules.applications.service import ApplicationService
from app.modules.groups.repository import GroupRoleRepository, GroupUserRepository, UserRoleRepository
from app.modules.permissions.repository import RolePermissionRepository
from app.modules.permissions.schemas import PermissionRead
from app.modules.roles.schemas import RoleRead
from app.modules.users.repository import UserRepository


class AuthorizationService:
    def __init__(self, session: Session):
        self.session = session
        self.user_repo = UserRepository(session)
        self.user_role_repo = UserRoleRepository(session)
        self.group_user_repo = GroupUserRepository(session)
        self.group_role_repo = GroupRoleRepository(session)
        self.role_perm_repo = RolePermissionRepository(session)
        self.app_service = ApplicationService(session)

    def _get_effective_roles(self, user_id: str) -> list:
        direct_roles = self.user_role_repo.list_roles_for_user(user_id)
        group_ids = self.group_user_repo.list_groups_for_user(user_id)
        group_roles = []
        for gid in group_ids:
            group_roles.extend(self.group_role_repo.list_roles_for_group(gid))
        return list({r.id: r for r in direct_roles + group_roles}.values())

    def _get_effective_permissions_for_roles(self, roles: list) -> list:
        all_perms = []
        for role in roles:
            perms = self.role_perm_repo.list_permissions_by_role(role.id)
            all_perms.extend(perms)
        return list({p.id: p for p in all_perms}.values())

    def is_minerva_admin(self, user_id: str) -> bool:
        """True si el usuario tiene el rol global de administrador de Minerva."""
        roles = self._get_effective_roles(user_id)
        return any(r.slug == "minerva.admin" for r in roles)

    def check_permission(self, user_id: str, application_slug: str, permission_slug: str) -> dict:
        app = self.app_service.get_application_by_slug(application_slug)
        if not app:
            raise NotFoundError(detail="Aplicación no encontrada")

        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError(detail="Usuario no encontrado")

        if user.status != "active":
            return {"allowed": False, "reason": "Usuario inactivo", "application_id": app.id}

        roles = self._get_effective_roles(user_id)
        app_roles = [r for r in roles if r.application_id == app.id]
        effective_perms = self._get_effective_permissions_for_roles(app_roles)
        has_perm = any(p.slug == permission_slug for p in effective_perms)
        if has_perm:
            return {"allowed": True, "reason": "User has permission through assigned roles", "application_id": app.id}
        return {"allowed": False, "reason": "No tiene el permiso requerido", "application_id": app.id}

    def get_me_permissions(self, user_id: str, application_slug: str) -> dict:
        app = self.app_service.get_application_by_slug(application_slug)
        if not app:
            raise NotFoundError(detail="Aplicación no encontrada")

        roles = self._get_effective_roles(user_id)
        app_roles = [r for r in roles if r.application_id == app.id]
        effective_perms = self._get_effective_permissions_for_roles(app_roles)

        return {
            "user_id": user_id,
            "application_slug": application_slug,
            "roles": [RoleRead.model_validate(r) for r in app_roles],
            "permissions": [PermissionRead.model_validate(p) for p in effective_perms],
        }
