import logging
from datetime import datetime, timezone

from sqlmodel import Session

from app.core.config import settings
from app.core.exceptions import BadRequestError, ForbiddenError, NotFoundError
from app.core.security import create_access_token, verify_secret
from app.modules.applications.repository import ApplicationRepository
from app.modules.applications.service import ApplicationService
from app.modules.auth.repository import AuthCodeRepository
from app.modules.auth.schemas import AuthRegister
from app.modules.groups.repository import GroupRoleRepository, GroupUserRepository, UserRoleRepository
from app.modules.permissions.repository import RolePermissionRepository
from app.modules.users.repository import UserRepository
from app.modules.users.service import UserService

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(self, session: Session):
        self.session = session
        self.user_service = UserService(session)
        self.user_repo = UserRepository(session)
        self.auth_code_repo = AuthCodeRepository(session)
        self.app_service = ApplicationService(session)
        self.app_repo = ApplicationRepository(session)
        self.user_role_repo = UserRoleRepository(session)
        self.group_user_repo = GroupUserRepository(session)
        self.group_role_repo = GroupRoleRepository(session)
        self.role_perm_repo = RolePermissionRepository(session)

    def register(self, data: AuthRegister) -> dict:
        from app.modules.users.schemas import UserCreate

        user_data = UserCreate(email=data.email, full_name=data.full_name, password=data.password)
        user = self.user_service.create_user(user_data)
        token = create_access_token(user.id, user.email, user.full_name)
        return {"access_token": token, "token_type": "bearer", "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60}

    def login(self, email: str, password: str) -> dict:
        token = self.user_service.authenticate(email, password)
        user = self.user_repo.get_by_email(email)
        user.last_login_at = datetime.now(timezone.utc)
        self.user_repo.update(user)
        return {"access_token": token, "token_type": "bearer", "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60}

    def get_me(self, user_id: str) -> dict:
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError(detail="Usuario no encontrado")

        direct_roles = self.user_role_repo.list_roles_for_user(user_id)
        group_ids = self.group_user_repo.list_groups_for_user(user_id)
        group_roles = []
        for gid in group_ids:
            group_roles.extend(self.group_role_repo.list_roles_for_group(gid))

        all_roles = list({r.id: r for r in direct_roles + group_roles}.values())

        all_permissions = []
        for role in all_roles:
            all_permissions.extend(self.role_perm_repo.list_permissions_by_role(role.id))

        return {
            "user": {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "auth_provider": user.auth_provider,
                "status": user.status,
            },
            "roles": [
                {"id": r.id, "name": r.name, "slug": r.slug, "application_id": r.application_id} for r in all_roles
            ],
            "permissions": [
                {"id": p.id, "name": p.name, "slug": p.slug, "application_id": p.application_id}
                for p in all_permissions
            ],
        }

    def authorize(self, client_id: str, redirect_uri: str, user_id: str, state: str, scope: str) -> str:
        app = self.app_service.get_application_by_client_id(client_id)
        if not app:
            raise BadRequestError(detail="Aplicación no encontrada")
        if app.status != "active":
            raise ForbiddenError(detail="Aplicación inactiva")

        if not self.app_service.validate_redirect_uri(client_id, redirect_uri):
            raise BadRequestError(detail="redirect_uri no autorizada para esta aplicación")

        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError(detail="Usuario no encontrado")
        if user.status != "active":
            raise ForbiddenError(detail="Usuario inactivo")

        auth_code = self.auth_code_repo.create_code(client_id, user_id, redirect_uri, scope)
        return redirect_uri + f"?code={auth_code.code}&state={state}"

    def exchange_token(self, client_id: str, client_secret: str, code: str, redirect_uri: str) -> dict:
        app = self.app_service.get_application_by_client_id(client_id)
        if not app:
            raise BadRequestError(detail="Aplicación no encontrada")

        if not verify_secret(client_secret, app.client_secret_hash):
            raise ForbiddenError(detail="client_secret inválido")

        auth_code = self.auth_code_repo.get_by_code(code)
        if not auth_code:
            raise BadRequestError(detail="Código de autorización inválido o ya usado")

        # expires_at se guarda en una columna sin timezone, por lo que vuelve naive;
        # lo normalizamos a UTC para poder compararlo con un datetime aware.
        expires_at = auth_code.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires_at:
            raise BadRequestError(detail="Código de autorización expirado")

        user = self.user_repo.get_by_id(auth_code.user_id)
        if not user:
            raise NotFoundError(detail="Usuario no encontrado")

        self.auth_code_repo.mark_used(auth_code)

        all_perms, all_role_slugs = self._get_user_permissions(user.id, app.slug)
        token = create_access_token(
            user_id=user.id,
            email=user.email,
            name=user.full_name,
            application_slug=app.slug,
            roles=all_role_slugs,
            permissions=all_perms,
        )
        return {"access_token": token, "token_type": "bearer", "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60}

    def _get_user_permissions(self, user_id: str, app_slug: str) -> tuple[list[str], list[str]]:
        direct_roles = self.user_role_repo.list_roles_for_user(user_id)
        group_ids = self.group_user_repo.list_groups_for_user(user_id)
        group_roles = []
        for gid in group_ids:
            group_roles.extend(self.group_role_repo.list_roles_for_group(gid))
        all_roles = list({r.id: r for r in direct_roles + group_roles}.values())
        app_roles = [r for r in all_roles if self._app_slug_by_id(r.application_id) == app_slug]
        permissions = []
        for role in app_roles:
            for perm in self.role_perm_repo.list_permissions_by_role(role.id):
                if perm.application_id == role.application_id:
                    permissions.append(perm.slug)
        return permissions, [r.slug for r in app_roles]

    def _app_slug_by_id(self, app_id: str) -> str:
        app = self.app_repo.get_by_id(app_id)
        if app:
            return app.slug
        return ""
