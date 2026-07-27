from sqlmodel import Session

from app.core.config import settings
from app.core.exceptions import ForbiddenError, NotFoundError
from app.modules.applications.repository import ApplicationRepository
from app.modules.devkit.manifest import ManifestLoader
from app.modules.devkit.schemas import (
    DevLoginRequest,
    ManifestImportResult,
    MePermissionsResponse,
    MeResponse,
    TokenResponse,
)
from app.modules.groups.repository import GroupRoleRepository, GroupUserRepository, UserRoleRepository
from app.modules.oidc.service import OIDCService
from app.modules.permissions.repository import RolePermissionRepository
from app.modules.users.models import User
from app.modules.users.repository import UserRepository


class DevKitService:
    def __init__(self, session: Session):
        self.session = session
        self.user_repo = UserRepository(session)
        self.app_repo = ApplicationRepository(session)
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

        token = OIDCService(self.session).issue_dev_token(
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

    def _require_application_access(self, current_user: dict, application_code: str) -> None:
        """El token solo puede consultar la app para la que fue emitido: `aud` en
        access tokens de consumidor, `applications` en tokens dev (issue #64). Sin
        esto, un token con aud=A podía leer permisos reales de una app B ajena."""
        if current_user.get("typ") == "dev":
            allowed = application_code in current_user.get("applications", [])
        else:
            allowed = current_user.get("aud") == application_code
        if not allowed:
            raise ForbiddenError(detail="El token no está autorizado para esta aplicación")

    def get_me_permissions(self, current_user: dict, application_code: str) -> MePermissionsResponse:
        app = self.app_repo.get_by_slug(application_code)
        if not app:
            raise NotFoundError(detail="Aplicación no encontrada")
        self._require_application_access(current_user, application_code)

        roles = [r for r in self._effective_roles(current_user["sub"]) if r.application_id == app.id]
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

    # --- Manifests --------------------------------------------------------
    def import_manifest(self, content: str, source: str = "manifest.minerva.yml") -> ManifestImportResult:
        return ManifestLoader(self.session).import_manifest(content, source)
