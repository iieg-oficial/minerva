from sqlmodel import Session

from app.core.config import settings
from app.core.exceptions import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.core.security import create_dev_token
from app.modules.applications.repository import ApplicationRepository
from app.modules.devkit.manifest import ManifestLoader
from app.modules.devkit.schemas import (
    AccessAssignmentRead,
    DevLoginRequest,
    ManifestImportResult,
    MePermissionsResponse,
    MeResponse,
    TokenResponse,
)
from app.modules.groups.models import UserRole
from app.modules.groups.repository import GroupRoleRepository, GroupUserRepository, UserRoleRepository
from app.modules.permissions.repository import RolePermissionRepository
from app.modules.roles.repository import RoleRepository
from app.modules.users.models import User
from app.modules.users.repository import UserRepository


class DevKitService:
    def __init__(self, session: Session):
        self.session = session
        self.user_repo = UserRepository(session)
        self.app_repo = ApplicationRepository(session)
        self.role_repo = RoleRepository(session)
        self.user_role_repo = UserRoleRepository(session)
        self.group_user_repo = GroupUserRepository(session)
        self.group_role_repo = GroupRoleRepository(session)
        self.role_perm_repo = RolePermissionRepository(session)

    # --- Helpers ----------------------------------------------------------
    def _effective_roles(self, user_id: str) -> list:
        direct = self.user_role_repo.list_roles_for_user(user_id)
        group_ids = self.group_user_repo.list_groups_for_user(user_id)
        group_roles = []
        for gid in group_ids:
            group_roles.extend(self.group_role_repo.list_roles_for_group(gid))
        return list({r.id: r for r in direct + group_roles}.values())

    def _app_slug(self, app_id: str) -> str:
        app = self.app_repo.get_by_id(app_id)
        return app.slug if app else ""

    # --- Dev login --------------------------------------------------------
    def dev_login(self, data: DevLoginRequest) -> TokenResponse:
        if not settings.MINERVA_ENABLE_DEV_LOGIN:
            raise ForbiddenError(detail="El login de desarrollo está deshabilitado (MINERVA_ENABLE_DEV_LOGIN=false)")

        user = self.user_repo.get_by_email(data.email)
        if not user:
            # En modo dev se crea el usuario automáticamente para agilizar pruebas.
            user = User(
                email=data.email,
                full_name=data.full_name or data.email.split("@")[0],
                auth_provider="dev",
                status="active",
            )
            user = self.user_repo.create(user)

        if user.status != "active":
            raise ForbiddenError(detail="Usuario inactivo")

        roles = self._effective_roles(user.id)
        roles_by_app: dict[str, list[str]] = {}
        for role in roles:
            slug = self._app_slug(role.application_id)
            roles_by_app.setdefault(slug, []).append(role.name)

        token = create_dev_token(
            user_id=user.id,
            email=user.email,
            name=user.full_name,
            applications=list(roles_by_app.keys()),
            roles_by_application=roles_by_app,
        )
        return TokenResponse(
            access_token=token,
            token_type="bearer",
            expires_in=settings.effective_token_expire_minutes * 60,
        )

    # --- Me ---------------------------------------------------------------
    def get_me(self, user_id: str) -> MeResponse:
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError(detail="Usuario no encontrado")
        return MeResponse(id=user.id, email=user.email, full_name=user.full_name, status=user.status)

    def get_me_permissions(self, user_id: str, application_code: str) -> MePermissionsResponse:
        app = self.app_repo.get_by_slug(application_code)
        if not app:
            raise NotFoundError(detail="Aplicación no encontrada")

        roles = [r for r in self._effective_roles(user_id) if r.application_id == app.id]
        permissions: set[str] = set()
        for role in roles:
            for perm in self.role_perm_repo.list_permissions_by_role(role.id):
                if perm.application_id == app.id:
                    permissions.add(perm.slug)

        return MePermissionsResponse(
            application=application_code,
            roles=[r.name for r in roles],
            permissions=sorted(permissions),
        )

    # --- Access assignments ----------------------------------------------
    def list_access_assignments(
        self, user_id: str | None = None, application_code: str | None = None
    ) -> list[AccessAssignmentRead]:
        from sqlmodel import select

        statement = select(UserRole)
        if user_id:
            statement = statement.where(UserRole.user_id == user_id)
        assignments = self.session.exec(statement).all()

        result: list[AccessAssignmentRead] = []
        for ur in assignments:
            role = self.role_repo.get_by_id(ur.role_id)
            if not role:
                continue
            app_code = self._app_slug(role.application_id)
            if application_code and app_code != application_code:
                continue
            result.append(
                AccessAssignmentRead(
                    id=f"{ur.user_id}:{ur.role_id}",
                    user_id=ur.user_id,
                    role_id=ur.role_id,
                    role_name=role.name,
                    role_slug=role.slug,
                    application_id=role.application_id,
                    application_code=app_code,
                )
            )
        return result

    def create_access_assignment(self, user_id: str, role_id: str) -> AccessAssignmentRead:
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError(detail="Usuario no encontrado")
        role = self.role_repo.get_by_id(role_id)
        if not role:
            raise NotFoundError(detail="Rol no encontrado")

        if self.user_role_repo.get(user_id, role_id):
            raise ConflictError(detail="El rol ya está asignado a este usuario")

        self.user_role_repo.add(UserRole(user_id=user_id, role_id=role_id))
        return AccessAssignmentRead(
            id=f"{user_id}:{role_id}",
            user_id=user_id,
            role_id=role_id,
            role_name=role.name,
            role_slug=role.slug,
            application_id=role.application_id,
            application_code=self._app_slug(role.application_id),
        )

    def delete_access_assignment(self, assignment_id: str) -> None:
        if ":" not in assignment_id:
            raise BadRequestError(detail="Identificador de asignación inválido (formato user_id:role_id)")
        user_id, role_id = assignment_id.split(":", 1)
        ur = self.user_role_repo.get(user_id, role_id)
        if not ur:
            raise NotFoundError(detail="Asignación no encontrada")
        self.user_role_repo.remove(ur)

    # --- Manifests --------------------------------------------------------
    def import_manifest(self, content: str, source: str = "manifest.minerva.yml") -> ManifestImportResult:
        return ManifestLoader(self.session).import_manifest(content, source)
